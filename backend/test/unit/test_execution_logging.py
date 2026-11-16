import asyncio
import logging

import httpx
import pytest
from loguru import logger

from app.core.config import Settings
from app.core.logging import InterceptHandler, configure_logging, console_format, traced


@pytest.mark.asyncio
async def test_concurrent_node_context_and_result_redaction():
    records = []
    sink = logger.add(lambda message: records.append(message.record))

    @traced("node", agent="resume_evaluation", node_arg="name", state_arg="state")
    async def node(name, state):
        await asyncio.sleep(0)
        logger.info("model.request")
        return {
            "analysis": {
                "name": "PRIVATE_NAME",
                "evidence": [{"quote": "PRIVATE_RESUME"}],
            },
            "summary": {"total_score": 75, "recommendation": "recommended"},
        }

    try:
        await asyncio.gather(
            node("verify_hard_conditions", {"candidate_id": 1}),
            node("calculate_score", {"candidate_id": 2}),
        )
        calls = [r for r in records if r["message"] == "model.request"]
        assert {(r["extra"]["candidate_id"], r["extra"]["node"]) for r in calls} == {
            (1, "verify_hard_conditions"),
            (2, "calculate_score"),
        }
        completed = [r for r in records if r["message"] == "node.completed"]
        assert all(r["extra"]["duration_ms"] >= 0 for r in completed)
        assert all(r["extra"]["result"]["total_score"] == 75 for r in completed)
        assert "PRIVATE" not in str(records)
    finally:
        logger.remove(sink)


@pytest.mark.asyncio
async def test_failure_does_not_log_exception_payload_and_human_pause_is_not_error():
    records = []
    sink = logger.add(lambda message: records.append(message.record))

    @traced("node")
    async def fail():
        raise ValueError("PRIVATE_API_KEY_AND_RESUME")

    try:
        with pytest.raises(ValueError):
            await fail()
        failure = next(r for r in records if r["message"] == "node.failed")
        assert failure["extra"]["error_type"] == "ValueError"
        assert failure["extra"]["stack"]
        assert "PRIVATE" not in str(records)
    finally:
        logger.remove(sink)


def test_log_files_and_stdlib_exception_redaction(tmp_path):
    from app.core import logging as tracing

    original_handlers = logging.root.handlers[:]
    try:
        configure_logging(Settings(_env_file=None, log_dir=tmp_path))
        logger.bind(candidate_id=99, node="screen_hard_conditions").info("node.started")
        try:
            raise RuntimeError("PRIVATE_DATABASE_PAYLOAD")
        except RuntimeError:
            record = logging.LogRecord(
                "app.test",
                logging.ERROR,
                __file__,
                1,
                "node.failed",
                (),
                __import__("sys").exc_info(),
            )
            InterceptHandler().emit(record)
        assert "node.started" in (tmp_path / "hireagent.log").read_text(
            encoding="utf-8"
        )
        errors = (tmp_path / "errors.log").read_text(encoding="utf-8")
        assert "node.failed" in errors and "RuntimeError" in errors
        assert "PRIVATE_DATABASE_PAYLOAD" not in errors
        assert "\x1b[" not in errors
        assert "\x1b[" not in (tmp_path / "hireagent.log").read_text(encoding="utf-8")
    finally:
        for sink in tracing._sinks:
            logger.remove(sink)
        tracing._sinks = []
        logging.root.handlers = original_handlers


@pytest.mark.asyncio
async def test_request_id_is_returned_and_query_values_are_not_logged():
    from app.main import create_app

    app = create_app(Settings(_env_file=None))

    @app.get("/test-log-correlation")
    async def endpoint():
        logger.info("test.endpoint")
        return {"ok": True}

    records = []
    sink = logger.add(lambda message: records.append(message.record))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/test-log-correlation?secret=PRIVATE_QUERY")
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 32
        matching = [
            r for r in records if r["message"] in ("test.endpoint", "http.completed")
        ]
        assert len(matching) == 2
        assert all(r["extra"]["request_id"] == request_id for r in matching)
        assert "PRIVATE_QUERY" not in str(records)
    finally:
        logger.remove(sink)


@pytest.mark.parametrize(
    "event,color",
    [
        ("node.started", "36"),
        ("node.completed", "32"),
        ("node.cache_hit", "32"),
        ("human_review.waiting_for_human", "33"),
        ("model.retry_schema", "33"),
        ("node.failed", "31"),
    ],
)
def test_console_event_colors_and_safe_value_formatting(event, color):
    messages = []
    sink = logger.add(messages.append, format=console_format, colorize=True)
    try:
        logger.bind(
            agent="resume_evaluation",
            candidate_id=123,
            node="verify_hard_conditions",
            duration_ms=12.5,
            model="literal{model}<red>value</red>",
        ).info(event)
        rendered = str(messages[-1])
        assert f"\x1b[{color}m{event}\x1b[0m" in rendered
        assert "12.50ms" in rendered
        assert "candidate=123" in rendered
        assert "literal{model}<red>value</red>" in rendered
    finally:
        logger.remove(sink)


def test_no_color_environment_overrides_enabled_color_setting(tmp_path, monkeypatch):
    import io

    from app.core import logging as tracing

    stream = io.StringIO()
    original_handlers = logging.root.handlers[:]
    monkeypatch.setattr(tracing.sys, "stderr", stream)
    monkeypatch.setenv("NO_COLOR", "1")
    try:
        configure_logging(Settings(_env_file=None, log_dir=tmp_path, log_colorize=True))
        logger.bind(agent="interview", node="auto_approve").success("node.completed")
        assert "node.completed" in stream.getvalue()
        assert "\x1b[" not in stream.getvalue()
    finally:
        for sink in tracing._sinks:
            logger.remove(sink)
        tracing._sinks = []
        logging.root.handlers = original_handlers
