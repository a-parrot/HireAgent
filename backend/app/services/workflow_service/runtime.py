import asyncio
import logging
from contextlib import AsyncExitStack

from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.types import Command, interrupt
from sqlalchemy import select, text

from app.agents.recruitment_agent.nodes.analysis import (
    CandidateEvaluationAgent,
    EvaluationReviewAgent,
    ResumeAnalysisAgent,
)
from app.agents.recruitment_agent.nodes.summarize_result import summarize
from app.agents.recruitment_agent.recruitment_graph import build_graph
from app.clients.llm_client import LLMClient
from app.core.errors import BusinessError
from app.models.mysql.entities import (
    Batch,
    Candidate,
    Event,
    NodeExecution,
    Review,
    utcnow,
)
from app.repositories.common import require
from app.services.resume_service.resumes import parse_pdf


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

    async def start(self):
        # Hold a dedicated connection: a second worker must not recover the same tasks.
        connection = await self.stack.enter_async_context(self.db.engine.connect())
        lock_name = f"hireagent:{self.config.db_name}"[:64]
        if (
            await connection.scalar(
                text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}
            )
            != 1
        ):
            raise RuntimeError("已有后端实例运行；请使用单 worker")
        self.runtime_connection = connection
        self.lock_name = lock_name
        # Fail clearly before accepting requests if migrations have not been applied.
        from app.models.mysql.entities import Base

        async with self.db.session() as session:
            for table in Base.metadata.sorted_tables:
                await session.execute(select(table.c.id).limit(1))
        uri = self.db.engine.url.render_as_string(hide_password=False)
        saver = await self.stack.enter_async_context(
            AIOMySQLSaver.from_conn_string(uri)
        )
        await saver.setup()
        self.graph = build_graph(self, saver)
        await self.recover()

    async def recover(self):
        """Repair persisted batch status even if no candidate needs to run again."""
        async with self.db.session() as session:
            rows = (
                await session.scalars(
                    select(Candidate).where(
                        Candidate.processing_status.in_(["running", "waiting_review"])
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
        for candidate_id in ids:
            self.enqueue(candidate_id)

    def enqueue(self, candidate_id):
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

    async def execute_node(self, name, state):
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
                return row.output_data
            if row is None:
                row = NodeExecution(candidate_id=candidate_id, node_name=name)
                session.add(row)
            row.status, row.started_at = "running", utcnow()
            row.attempt_count = (row.attempt_count or 0) + 1
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
            file_id = candidate.file_id
        rules = await self.rules(candidate_id)
        if name == "parse_pdf":
            async with self.file_locks.setdefault(file_id, asyncio.Lock()):
                output = {"pages": await parse_pdf(self.db, self.config, file_id)}
        elif name == "analyze_resume":
            output = {
                "analysis": await ResumeAnalysisAgent().run(
                    self.llm, rules, state["pages"], self.config.llm_page_chars
                )
            }
        elif name == "evaluate_candidate":
            output = {
                "evaluation": await CandidateEvaluationAgent().run(
                    self.llm, rules, state["analysis"]
                )
            }
        elif name == "review_evaluation":
            output = {
                "verification": await EvaluationReviewAgent().run(
                    self.llm, rules, state["analysis"], state["evaluation"]
                )
            }
        else:
            output = {
                "summary": summarize(
                    rules,
                    state["pages"],
                    state["analysis"],
                    state["evaluation"],
                    state["verification"],
                )
            }
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
            if name == "analyze_resume":
                candidate.name = output["analysis"]["name"]
                candidate.extracted_facts = output["analysis"]["facts"]
                candidate.evidence = output["analysis"]["evidence"]
                candidate.model_id = self.config.llm_model
                candidate.prompt_versions = {
                    "analysis": "1",
                    "evaluation": "1",
                    "review": "1",
                }
            elif name == "evaluate_candidate":
                candidate.hard_conditions = output["evaluation"]["hard_conditions"]
                candidate.dimension_scores = output["evaluation"]["dimension_scores"]
                candidate.missing_fields = output["evaluation"]["missing_fields"]
                candidate.risks = output["evaluation"]["risks"]
            elif name == "summarize_result":
                for key, value in output["summary"].items():
                    setattr(candidate, key, value)
                candidate.processing_status = (
                    "completed"
                    if candidate.recommendation == "deferred"
                    else "waiting_review"
                )
                if candidate.processing_status == "waiting_review":
                    candidate.current_node = "human_review"
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

    async def human_review(self, state):
        decision = interrupt(
            {
                "candidate_id": str(state["candidate_id"]),
                "message": "等待人工批准或暂缓",
            }
        )
        async with self.db.session() as session:
            candidate = await require(session, Candidate, state["candidate_id"])
            if candidate.review_status not in ("approved", "deferred"):
                raise BusinessError("尚无有效人工决定", 409)
            if decision["operation"] != (
                "approve" if candidate.review_status == "approved" else "defer"
            ):
                raise BusinessError("恢复决定与审批记录不一致", 409)
        return {"decision": decision["operation"]}

    async def run(self, candidate_id):
        async with self.locks.setdefault(candidate_id, asyncio.Lock()), self.semaphore:
            try:
                async with self.db.session() as session:
                    candidate = await require(session, Candidate, candidate_id)
                    workflow_id = candidate.workflow_id
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
                result = await self.graph.ainvoke(value, config)
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
                        )
                    )
            finally:
                await self.refresh_batch(candidate_id)

    async def refresh_batch(self, candidate_id):
        async with self.db.session() as session:
            candidate = await require(session, Candidate, candidate_id)
            batch_id = candidate.batch_id
        await self.refresh_batch_id(batch_id)

    async def refresh_batch_id(self, batch_id):
        async with self.db.session() as session:
            batch = await require(session, Batch, batch_id, lock=True)
            active = await session.scalar(
                select(Candidate.id)
                .where(
                    Candidate.batch_id == batch.id,
                    Candidate.processing_status.in_(["pending", "running"]),
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
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        try:
            await self.llm.close()
        finally:
            try:
                if hasattr(self, "runtime_connection"):
                    await self.runtime_connection.execute(
                        text("SELECT RELEASE_LOCK(:name)"), {"name": self.lock_name}
                    )
            finally:
                await self.stack.aclose()
