"""Tracked import jobs, durable progress and cross-process MySQL file locks."""

import asyncio
import copy
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import select, text

from app.agents.import_agent.import_graph import build_import_graph
from app.core.errors import BusinessError
from app.models.mysql.entities import File, FileImportTask, utcnow
from app.repositories.common import require
from app.services.resume_service.resumes import parse_pdf, safe_path
from app.services.resume_service.workspace import file_sha

logger = logging.getLogger(__name__)


def convert_word(config, source, target):
    binary = shutil.which(config.libreoffice_bin)
    if not binary:
        raise BusinessError(
            "DOCX 解析需要 LibreOffice，请在 Ubuntu 安装 libreoffice-writer 后重试，或上传 PDF"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        profile = (work / "profile").as_uri()
        try:
            result = subprocess.run(
                [
                    binary,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(work),
                    str(source),
                ],
                check=False,
                capture_output=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise BusinessError("Word 转 PDF 超时，请改用 PDF 后重试") from exc
        converted = work / (source.stem + ".pdf")
        if result.returncode or not converted.is_file():
            raise BusinessError("Word 转 PDF 失败，请检查原件")
        shutil.copyfile(converted, target)


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
            return
        for tid in ids:
            if tid not in self.tasks:
                task = asyncio.create_task(self.run(tid))
                self.tasks[tid] = task
                task.add_done_callback(lambda _, key=tid: self.tasks.pop(key, None))

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

    async def close(self):
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def run(self, tid):
        async with self.semaphore:
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
                        task.node_progress = []
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
            finally:
                if connection is not None:
                    try:
                        if acquired:
                            await connection.execute(
                                text("SELECT RELEASE_LOCK(:key)"),
                                {"key": f"hireagent-import-{file_id}"},
                            )
                    finally:
                        await connection.close()

    async def execute(self, node, state):
        async with self.db.session() as s:
            task = await require(s, FileImportTask, state["task_id"])
            task.current_node = node
            progress = list(task.node_progress or [])
            progress.append(
                {
                    "name": node,
                    "status": "running",
                    "started_at": utcnow().isoformat() + "Z",
                }
            )
            task.node_progress = progress
            file = await require(s, File, state["file_id"])
            source = safe_path(self.config, file.storage_path)
            file_type = file.file_type
            digest = file.sha256
        result = {}
        if node == "prepare_import":
            if await asyncio.to_thread(file_sha, source) != digest:
                raise BusinessError(
                    "原件 SHA-256 与入库记录不一致，停止解析，请重新上传原件"
                )
            result = {"file_type": file_type}
        elif node in ("parse_pdf", "parse_word"):
            if node == "parse_word":
                relative = f"parsed/{state['file_id']}/preview.pdf"
                await asyncio.to_thread(
                    convert_word, self.config, source, safe_path(self.config, relative)
                )
                async with self.db.session() as s:
                    file = await require(s, File, state["file_id"])
                    file.preview_pdf_path = relative
            pages = await parse_pdf(
                self.db, self.config, state["file_id"], finalize=False
            )
            # parse_pdf is also used by legacy evaluation; workspace is ready only after all import nodes succeed.
            async with self.db.session() as s:
                file = await require(s, File, state["file_id"])
                file.parse_status = "running"
            result = {"pages": pages}
        elif node == "normalize_content":
            pages = state["pages"]
            root = f"parsed/{state['file_id']}"
            original = "\n\n".join(p["text"] for p in pages)
            normalized = "\n\n".join(
                f"<!-- page:{p['page_no']} -->\n" + p["text"].strip() for p in pages
            )
            paths = {
                "markdown_path": f"{root}/document.md",
                "normalized_markdown_path": f"{root}/normalized.md",
                "source_index_path": f"{root}/sources.json",
            }
            for key, content in (
                ("markdown_path", original),
                ("normalized_markdown_path", normalized),
                (
                    "source_index_path",
                    json.dumps(
                        [
                            {
                                "file_id": str(state["file_id"]),
                                "page_no": p["page_no"],
                                "text_path": f"page_texts/{state['file_id']}/{p['page_no']}.txt",
                            }
                            for p in pages
                        ],
                        ensure_ascii=False,
                    ),
                ),
            ):
                path = safe_path(self.config, paths[key])
                path.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(path.write_text, content, encoding="utf-8")
            async with self.db.session() as s:
                file = await require(s, File, state["file_id"])
                for key, value in paths.items():
                    setattr(file, key, value)
        elif node == "save_import_result":
            import pymupdf

            async with self.db.session() as s:
                file = await require(s, File, state["file_id"])
                file.parser_name = (
                    "libreoffice+pymupdf" if file_type == "docx" else "pymupdf"
                )
                file.parser_version = f"import-v1/pymupdf-{pymupdf.VersionBind}"
        async with self.db.session() as s:
            task = await require(s, FileImportTask, state["task_id"])
            progress = list(task.node_progress or [])
            progress[-1] = {
                **progress[-1],
                "status": "completed",
                "finished_at": utcnow().isoformat() + "Z",
            }
            task.node_progress = progress
        return result
