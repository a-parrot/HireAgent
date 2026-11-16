import asyncio
import logging
from contextlib import AsyncExitStack

from langgraph.types import Command
from sqlalchemy import select, text

from app.agents.interview_agent.agent import InterviewAgent
from app.agents.recruitment_agent.nodes import NODES
from app.agents.recruitment_agent.recruitment_graph import build_graph
from app.clients.checkpoint_client import checkpoint_saver, database_error_code
from app.clients.llm_client import LLMClient
from app.core.errors import BusinessError
from app.core.logging import error_fields, logger, summary, traced
from app.models.mysql.entities import (
    Batch,
    Candidate,
    Event,
    NodeExecution,
    Review,
    utcnow,
)
from app.repositories.common import require
from app.repositories.evaluation_repo.visibility import is_deleted, visible_candidates


class WorkflowRuntime:
    def __init__(self, db, config):
        self.db, self.config = db, config
        self.llm = LLMClient(config)
        self.tasks = {}
        self.locks = {}
        self.file_locks = {}
        self.semaphore = asyncio.Semaphore(config.model_concurrency)
        self.stack = AsyncExitStack()
        self.graph = None
        self.imports = None
        self.closed = False
        self.lock_lost = False
        self.heartbeat_task = None
        self.on_lock_lost = None

    async def start(self):
        await self.acquire_runtime_lock()
        # Fail clearly before accepting requests if migrations have not been applied.
        from app.models.mysql.entities import Base

        async with self.db.session() as session:
            for table in Base.metadata.sorted_tables:
                await session.execute(
                    select(next(iter(table.primary_key.columns))).limit(1)
                )
        saver = await self.stack.enter_async_context(checkpoint_saver(self.config))
        await saver.setup()
        self.graph = build_graph(self, saver)
        self.ensure_active()
        await self.recover()
        self.ensure_active()

    async def acquire_runtime_lock(self):
        # Hold a dedicated connection: a second worker must not recover the same tasks.
        connection = await self.stack.enter_async_context(self.db.engine.connect())
        # A rollback/return to the pool does not release a MySQL named lock.
        # Physically discard this connection even if startup or RELEASE_LOCK fails.
        self.stack.push_async_callback(connection.invalidate)
        await connection.execute(
            text("SET SESSION wait_timeout = :seconds"),
            {"seconds": self.config.runtime_lock_idle_timeout},
        )
        lock_name = f"hireagent:{self.config.db_name}"[:64]
        acquired = await connection.scalar(
            text("SELECT GET_LOCK(:name, :wait)"),
            {"name": lock_name, "wait": self.config.startup_lock_wait_seconds},
        )
        if acquired is None:
            raise RuntimeError("MySQL 工作流运行锁获取失败，请检查数据库连接和锁函数")
        if acquired != 1:
            owner = await connection.scalar(
                text("SELECT IS_USED_LOCK(:name)"), {"name": lock_name}
            )
            raise RuntimeError(
                f"等待 {self.config.startup_lock_wait_seconds} 秒后，当前数据库的工作流运行锁仍被其他连接占用"
                f"（连接 ID：{owner if owner is not None else '未知'}）。"
                "请停止旧的 PyCharm、Uvicorn 或 Docker 后端实例，再启动一个单 worker 实例；"
                "本地与服务器使用同一个数据库时也不能同时启动。不要仅更换端口。"
            )
        self.runtime_connection = connection
        self.lock_name = lock_name
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def ensure_active(self):
        if self.closed or self.lock_lost:
            raise BusinessError("后端工作流运行锁已失效或调度已停止，请重启后端", 503)

    async def _heartbeat_loop(self):
        while not self.closed and not self.lock_lost:
            await asyncio.sleep(self.config.runtime_lock_heartbeat_interval)
            if not await self._heartbeat_once():
                return

    async def _heartbeat_once(self):
        if self.closed or self.lock_lost:
            return False
        try:
            async with asyncio.timeout(self.config.runtime_lock_heartbeat_timeout):
                owned = await self.runtime_connection.scalar(
                    text("SELECT IS_USED_LOCK(:name) = CONNECTION_ID()"),
                    {"name": self.lock_name},
                )
        except Exception:  # noqa: BLE001 - heartbeat boundary must fail closed
            await self._lose_lock("connection_unavailable")
            return False
        if owned != 1:
            await self._lose_lock("ownership_changed")
            return False
        return True

    async def _lose_lock(self, reason):
        if self.lock_lost:
            return
        self.lock_lost = True
        logging.getLogger(__name__).critical(
            "Runtime lock lost; scheduling stopped, backend restart required (%s)",
            reason,
        )
        for task in list(self.tasks.values()):
            if not task.done():
                task.cancel()
        if self.on_lock_lost is not None:
            try:
                self.on_lock_lost()
            except Exception:  # noqa: BLE001 - keep fencing even if one scheduler fails
                logging.getLogger(__name__).error(
                    "Failed to suspend dependent scheduler"
                )
        try:
            async with asyncio.timeout(self.config.runtime_lock_heartbeat_timeout):
                await self.runtime_connection.invalidate()
        except Exception:  # noqa: BLE001 - already fenced; shutdown retries cleanup
            logging.getLogger(__name__).error(
                "Failed to discard lost runtime lock connection"
            )

    async def recover(self):
        """Repair persisted batch status even if no candidate needs to run again."""
        async with self.db.session() as session:
            rows = (
                await session.scalars(
                    select(Candidate).where(
                        Candidate.processing_status.in_(["running", "waiting_review"]),
                        visible_candidates(),
                    )
                )
            ).all()
            # pending candidates in already started batches must also recover.
            rows += list(
                (
                    await session.scalars(
                        select(Candidate)
                        .join(Batch)
                        .where(
                            Candidate.processing_status == "pending",
                            Batch.started_at.is_not(None),
                            visible_candidates(),
                        )
                    )
                ).all()
            )
            ids = [
                r.id
                for r in rows
                if r.processing_status != "waiting_review"
                or r.review_status != "pending"
            ]
            batch_ids = list(
                (
                    await session.scalars(
                        select(Batch.id).where(Batch.started_at.is_not(None))
                    )
                ).all()
            )
        for batch_id in batch_ids:
            await self.refresh_batch_id(batch_id)
            await InterviewAgent().schedule_ready(self.db, batch_id)
        for candidate_id in ids:
            self.enqueue(candidate_id)

    def enqueue(self, candidate_id):
        self.ensure_active()
        task = self.tasks.get(candidate_id)
        if task and not task.done():
            return
        task = asyncio.create_task(self.run(candidate_id))
        self.tasks[candidate_id] = task
        task.add_done_callback(self._observe_task)

    @staticmethod
    def _observe_task(task):
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).error(
                "Background workflow could not persist status; restart recovery required (%s)",
                type(task.exception()).__name__,
            )

    async def rules(self, candidate_id):
        async with self.db.session() as session:
            candidate = await require(session, Candidate, candidate_id)
            batch = await require(session, Batch, candidate.batch_id)
            return batch.rule_snapshot

    async def report_progress(self, candidate_id, node, current, total):
        async with self.db.session() as session:
            row = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.candidate_id == candidate_id,
                    NodeExecution.node_name == node,
                    NodeExecution.status == "running",
                )
            )
            if row:
                row.output_data = {"progress": {"current": current, "total": total}}

    @traced("node", agent="resume_evaluation", node_arg="name", state_arg="state")
    async def execute_node(self, name, state):
        self.ensure_active()
        candidate_id = state["candidate_id"]
        async with self.db.session() as session:
            candidate = await require(session, Candidate, candidate_id)
            row = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.candidate_id == candidate_id,
                    NodeExecution.node_name == name,
                )
            )
            if row and row.status == "succeeded":
                logger.bind(result=summary(row.output_data)).info("node.cache_hit")
                return row.output_data
            if row is None:
                row = NodeExecution(candidate_id=candidate_id, node_name=name)
                session.add(row)
            row.status, row.started_at = "running", utcnow()
            row.attempt_count = (row.attempt_count or 0) + 1
            logger.bind(attempt=row.attempt_count, batch_id=candidate.batch_id).info(
                "node.executing"
            )
            candidate.current_node = name
            session.add(
                Event(
                    batch_id=candidate.batch_id,
                    candidate_id=candidate_id,
                    node_name=name,
                    event_type="started",
                    attempt_count=row.attempt_count,
                    message="节点开始",
                )
            )
        node = NODES[name]
        output = await node.run(self, state)
        async with self.db.session() as session:
            candidate = await require(session, Candidate, candidate_id)
            row = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.candidate_id == candidate_id,
                    NodeExecution.node_name == name,
                )
            )
            row.status, row.output_data, row.completed_at, row.error_message = (
                "succeeded",
                output,
                utcnow(),
                None,
            )
            save = getattr(node, "save", None)
            if save is not None:
                save(candidate, output, self.config)
            session.add(
                Event(
                    batch_id=candidate.batch_id,
                    candidate_id=candidate_id,
                    node_name=name,
                    event_type="completed",
                    message="节点完成",
                )
            )
        return output

    @traced("workflow", agent="recruitment", id_arg="candidate_id")
    async def run(self, candidate_id):
        async with self.locks.setdefault(candidate_id, asyncio.Lock()), self.semaphore:
            self.ensure_active()
            try:
                async with self.db.session() as session:
                    candidate = await require(session, Candidate, candidate_id)
                    if await is_deleted(session, candidate_id):
                        return
                    workflow_id = candidate.workflow_id
                    logger.bind(
                        workflow_id=workflow_id, batch_id=candidate.batch_id
                    ).info("workflow.state_loaded")
                    candidate.started_at = candidate.started_at or utcnow()
                    if candidate.review_status == "pending":
                        candidate.processing_status = "running"
                    candidate.error_message, candidate.error_node = None, None
                config = {"configurable": {"thread_id": workflow_id}}
                snapshot = await self.graph.aget_state(config)
                pending_decision = None
                async with self.db.session() as session:
                    review = await session.scalar(
                        select(Review)
                        .where(
                            Review.candidate_id == candidate_id,
                            Review.resume_status.in_(["pending", "failed"]),
                        )
                        .order_by(Review.review_version.desc())
                        .limit(1)
                    )
                    if review:
                        pending_decision = {"operation": review.operation}
                value = (
                    Command(resume=pending_decision)
                    if snapshot.interrupts and pending_decision
                    else None
                    if snapshot.values
                    else {"candidate_id": candidate_id}
                )
                if pending_decision:
                    logger.bind(operation=pending_decision["operation"]).info(
                        "workflow.resume_requested"
                    )
                result = await self.graph.ainvoke(value, config)
                logger.info(
                    "workflow.waiting_for_human"
                    if result.get("__interrupt__")
                    else "workflow.graph_completed"
                )
                if result.get("__interrupt__") and pending_decision:
                    result = await self.graph.ainvoke(
                        Command(resume=pending_decision), config
                    )
                async with self.db.session() as session:
                    candidate = await require(session, Candidate, candidate_id)
                    candidate.processing_status = (
                        "waiting_review" if result.get("__interrupt__") else "completed"
                    )
                    if candidate.processing_status == "completed":
                        candidate.completed_at = utcnow()
                        reviews = (
                            await session.scalars(
                                select(Review).where(
                                    Review.candidate_id == candidate_id,
                                    Review.resume_status.in_(["pending", "failed"]),
                                )
                            )
                        ).all()
                        for review in reviews:
                            review.resume_status, review.resume_error = (
                                "succeeded",
                                None,
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - background task boundary; persist safe failure
                logger.bind(**error_fields(exc)).error("workflow.execution_failed")
                # Exception text/tracebacks can contain provider payloads or SQL data.
                # Keep safe diagnostics instead of losing the exception type entirely.
                error_type = type(exc).__name__
                logging.getLogger(__name__).error(
                    "Workflow failed candidate_id=%s exception_type=%s db_error_code=%s",
                    candidate_id,
                    error_type,
                    database_error_code(exc),
                )
                message = (
                    exc.message
                    if isinstance(exc, BusinessError)
                    else "节点执行失败，请检查配置及服务日志"
                )
                async with self.db.session() as session:
                    candidate = await require(session, Candidate, candidate_id)
                    (
                        candidate.processing_status,
                        candidate.error_node,
                        candidate.error_message,
                    ) = "failed", candidate.current_node, message
                    row = await session.scalar(
                        select(NodeExecution).where(
                            NodeExecution.candidate_id == candidate_id,
                            NodeExecution.node_name == candidate.current_node,
                        )
                    )
                    if row and row.status != "succeeded":
                        row.status, row.error_message = "failed", message
                    reviews = (
                        await session.scalars(
                            select(Review).where(
                                Review.candidate_id == candidate_id,
                                Review.resume_status == "pending",
                            )
                        )
                    ).all()
                    for review in reviews:
                        review.resume_status, review.resume_error = "failed", message
                    session.add(
                        Event(
                            batch_id=candidate.batch_id,
                            candidate_id=candidate_id,
                            node_name=candidate.current_node,
                            event_type="failed",
                            level="error",
                            message=message,
                            details={
                                "exception_type": error_type,
                                "db_error_code": database_error_code(exc),
                            },
                        )
                    )
                return {"execution_status": "failed"}
            finally:
                await self.refresh_batch(candidate_id)

    async def refresh_batch(self, candidate_id):
        async with self.db.session() as session:
            candidate = await require(session, Candidate, candidate_id)
            batch_id = candidate.batch_id
        await self.refresh_batch_id(batch_id)
        await InterviewAgent().schedule_ready(self.db, batch_id)

    async def refresh_batch_id(self, batch_id):
        async with self.db.session() as session:
            batch = await require(session, Batch, batch_id, lock=True)
            active = await session.scalar(
                select(Candidate.id)
                .where(
                    Candidate.batch_id == batch.id,
                    Candidate.processing_status.in_(["pending", "running"]),
                    visible_candidates(),
                )
                .limit(1)
            )
            batch.status = "running" if active else "evaluation_done"
            if not active:
                batch.evaluation_completed_at = (
                    batch.evaluation_completed_at or utcnow()
                )
            else:
                batch.evaluation_completed_at = None

    async def close(self):
        if self.closed:
            return
        self.closed = True
        if self.heartbeat_task is not None:
            self.heartbeat_task.cancel()
            await asyncio.gather(self.heartbeat_task, return_exceptions=True)
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        try:
            await self.llm.close()
        finally:
            try:
                if hasattr(self, "runtime_connection") and not self.lock_lost:
                    await self.runtime_connection.execute(
                        text("SELECT RELEASE_LOCK(:name)"), {"name": self.lock_name}
                    )
            finally:
                await self.stack.aclose()
