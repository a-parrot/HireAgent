"""Tracked import jobs, durable progress and cross-process MySQL file locks."""

import asyncio
import copy
import logging

from sqlalchemy import select, text

from app.agents.resume_evaluation_agent.import_graph import build_import_graph
from app.agents.resume_evaluation_agent.nodes import IMPORT_NODES
from app.core.errors import BusinessError
from app.core.logging import error_fields, traced
from app.core.logging import logger as trace_logger
from app.models.mysql.entities import File, FileImportTask, utcnow
from app.repositories.common import require

logger = logging.getLogger(__name__)


class ImportRuntime:
    def __init__(self, db, config):
        self.db, self.config = db, config
        self.graph = build_import_graph(self)
        self.semaphore = asyncio.Semaphore(config.import_concurrency)
        self.tasks = {}
        self.file_locks = {}
        self.closing = False

    def submit(self, ids):
        if self.closing:
            raise BusinessError("解析调度已停止，请重启后端", 503)
        for tid in ids:
            if tid not in self.tasks:
                task = asyncio.create_task(self.run(tid))
                self.tasks[tid] = task
                task.add_done_callback(lambda _, key=tid: self.tasks.pop(key, None))

    async def ensure_parsed(self, file_id):
        from app.services.resume_service.workspace import queue_file

        async with self.db.session() as session:
            file = await require(session, File, file_id, lock=True)
            tid = await queue_file(session, file)
        if tid is not None:
            self.submit([tid])
            task = self.tasks.get(tid)
            if task is not None:
                await asyncio.shield(task)
        async with self.db.session() as session:
            file = await require(session, File, file_id)
            if file.parse_status != "completed":
                raise BusinessError(
                    file.parse_error or "PDF 解析尚未完成，请稍后重试", 409
                )

    async def start(self):
        async with self.db.session() as s:
            ids = list(
                await s.scalars(
                    select(FileImportTask.id).where(
                        FileImportTask.status.in_(["pending", "running"])
                    )
                )
            )
        self.submit(ids)

    def suspend(self):
        self.closing = True
        for task in list(self.tasks.values()):
            if not task.done():
                task.cancel()

    async def close(self):
        tasks = list(self.tasks.values())
        self.suspend()
        await asyncio.gather(*tasks, return_exceptions=True)

    @traced("import", agent="resume_import", id_arg="tid")
    async def run(self, tid):
        if self.closing:
            return
        async with self.semaphore:
            if self.closing:
                return
            connection = None
            acquired = False
            claimed = False
            file_id = None
            try:
                async with self.db.session() as s:
                    task = await require(s, FileImportTask, tid)
                    file_id = task.file_id
                lock = self.file_locks.setdefault(file_id, asyncio.Lock())
                async with lock:
                    if self.db.engine.dialect.name == "mysql":
                        connection = await self.db.engine.connect()
                        acquired = bool(
                            await connection.scalar(
                                text("SELECT GET_LOCK(:key,0)"),
                                {"key": f"hireagent-import-{file_id}"},
                            )
                        )
                        if not acquired:
                            return  # Another worker owns this file; its persisted status is authoritative.
                    async with self.db.session() as s:
                        file = await require(s, File, file_id, lock=True)
                        task = await require(s, FileImportTask, tid, lock=True)
                        if task.status not in ("pending", "running"):
                            return
                        task.status, task.started_at, task.finished_at = (
                            "running",
                            utcnow(),
                            None,
                        )
                        task.error_message = None
                        task.node_progress = list(task.node_progress or [])
                        file.parse_status, file.parse_error = "running", None
                        claimed = True
                    await self.graph.ainvoke({"file_id": file_id, "task_id": tid})
                    async with self.db.session() as s:
                        file = await require(s, File, file_id, lock=True)
                        task = await require(s, FileImportTask, tid, lock=True)
                        file.parse_status, file.parse_error, file.parsed_at = (
                            "completed",
                            None,
                            utcnow(),
                        )
                        task.status, task.finished_at, task.current_node = (
                            "completed",
                            utcnow(),
                            None,
                        )
            except (Exception, asyncio.CancelledError) as exc:
                if not isinstance(exc, asyncio.CancelledError):
                    trace_logger.bind(**error_fields(exc)).error(
                        "import.execution_failed"
                    )
                if claimed:
                    message = (
                        exc.message
                        if isinstance(exc, BusinessError)
                        else "导入被中断，可重新解析"
                        if isinstance(exc, asyncio.CancelledError)
                        else "解析失败，请检查原件或服务器日志后重试"
                    )
                    try:
                        async with self.db.session() as s:
                            task = await require(s, FileImportTask, tid)
                            file = await require(s, File, file_id)
                            task.status, task.error_message, task.finished_at = (
                                "failed",
                                message,
                                utcnow(),
                            )
                            progress = copy.deepcopy(task.node_progress or [])
                            for node in progress:
                                if node["status"] == "running":
                                    node.update(status="failed", error=message)
                            task.node_progress = progress
                            file.parse_status, file.parse_error = "failed", message
                    except Exception:
                        logger.exception(
                            "Unable to persist import failure task_id=%s", tid
                        )
                if not isinstance(exc, (BusinessError, asyncio.CancelledError)):
                    logger.exception("Import failed task_id=%s", tid)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                return {"execution_status": "failed"}
            finally:
                if connection is not None:
                    try:
                        if acquired:
                            await connection.execute(
                                text("SELECT RELEASE_LOCK(:key)"),
                                {"key": f"hireagent-import-{file_id}"},
                            )
                    finally:
                        try:
                            await connection.invalidate()
                        finally:
                            await connection.close()

    @traced("node", agent="resume_import", node_arg="node", state_arg="state")
    async def execute(self, node, state):
        async with self.db.session() as s:
            task = await require(s, FileImportTask, state["task_id"])
            task.current_node = node
            progress = copy.deepcopy(task.node_progress or [])
            position = next(
                (i for i, entry in enumerate(progress) if entry["name"] == node), None
            )
            previous = progress[position] if position is not None else {}
            entry = {
                **previous,
                "name": node,
                "status": "running",
                "started_at": utcnow().isoformat() + "Z",
            }
            entry.pop("remote_task", None)
            entry.pop("error", None)
            entry.pop("finished_at", None)
            if position is None:
                progress.append(entry)
            else:
                progress[position] = entry
            task.node_progress = progress
        result = await IMPORT_NODES[node].run(self, state)
        async with self.db.session() as s:
            task = await require(s, FileImportTask, state["task_id"])
            progress = copy.deepcopy(task.node_progress or [])
            for item in progress:
                if item["name"] == node:
                    item.update(
                        status="completed", finished_at=utcnow().isoformat() + "Z"
                    )
            task.node_progress = progress
        return result
