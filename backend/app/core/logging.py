"""Structured execution traces without resume text, credentials or model reasoning."""

import asyncio
import inspect
import logging
import os
import sys
import traceback
from functools import wraps
from time import perf_counter
from uuid import uuid4

from loguru import logger

_sinks = []
_DEFAULTS = {
    key: "-"
    for key in (
        "request_id",
        "agent",
        "candidate_id",
        "task_id",
        "file_id",
        "node",
        "workflow_id",
        "batch_id",
    )
}
logger.configure(extra=_DEFAULTS)
_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | req={extra[request_id]} agent={extra[agent]} candidate={extra[candidate_id]} task={extra[task_id]} node={extra[node]} | {message} | {extra}\n"

_CONSOLE_FIELDS = (
    "file_id",
    "workflow_id",
    "batch_id",
    "span_id",
    "method",
    "route",
    "http_status",
    "attempt",
    "model",
    "provider",
    "schema",
    "input_chars",
    "usage",
    "delay_seconds",
    "validation_issues",
    "result",
    "error_type",
    "db_error_code",
    "stack",
    "source",
    "operation",
    "review_version",
    "resume_status",
    "reservation_id",
    "scheduled",
    "candidate_ids",
    "action",
    "action_status",
)


def console_format(record):
    """Only trusted static color tags enter the format; log values remain placeholders."""
    event = record["message"]
    level = record["level"].no
    if level >= 40 or event.endswith((".failed", ".execution_failed")):
        event_color = "red"
    elif (
        level >= 30
        or ".retry_" in event
        or event.endswith((".waiting_for_human", ".cancelled"))
    ):
        event_color = "yellow"
    elif event.endswith(
        (".completed", ".schema_validated", ".booked", ".saved", ".cache_hit", ".ready")
    ):
        event_color = "green"
    else:
        event_color = "cyan"
    agent_color = {
        "recruitment": "magenta",
        "resume_import": "blue",
        "resume_evaluation": "cyan",
        "human_review": "yellow",
        "interview": "green",
    }.get(record["extra"].get("agent"), "white")
    line = (
        "<dim>{time:HH:mm:ss.SSS}</dim> | <level>{level:<8}</level> | "
        f"<{agent_color}>{{extra[agent]}}</{agent_color}> "
        "<dim>req={extra[request_id]:.8} candidate={extra[candidate_id]} task={extra[task_id]}</dim> "
        "| <bold>{extra[node]}</bold> | "
        f"<{event_color}>{{message}}</{event_color}>"
    )
    if isinstance(record["extra"].get("duration_ms"), (float, int)):
        line += " <yellow>{extra[duration_ms]:.2f}ms</yellow>"
    fields = [
        key
        for key in _CONSOLE_FIELDS
        if record["extra"].get(key) not in (None, "-", {})
    ]
    if fields:
        line += (
            "\n  <dim>"
            + "  ".join(f"{key}={{extra[{key}]}}" for key in fields)
            + "</dim>"
        )
    return line + "\n"


def error_fields(exc):
    """Keep exception type, driver code and stack locations, never exception values."""
    original = getattr(exc, "orig", exc)
    args = getattr(original, "args", ())
    return {
        "error_type": type(exc).__name__,
        "db_error_code": args[0] if args and type(args[0]) is int else None,
        "stack": [
            f"{frame.filename.rsplit(chr(92), 1)[-1].rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
            for frame in traceback.extract_tb(exc.__traceback__)[-12:]
        ],
    }


class InterceptHandler(logging.Handler):
    def emit(self, record):
        if record.name.startswith(("httpx", "httpcore", "sqlalchemy")):
            # Third-party messages may embed URLs, SQL or parameters.
            message = "library.event"
        else:
            message = record.getMessage()
        fields = {"source": record.name}
        if record.exc_info and record.exc_info[1]:
            fields.update(error_fields(record.exc_info[1]))
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.bind(**fields).log(level, message)


def configure_logging(settings):
    global _sinks
    for sink in _sinks:
        try:
            logger.remove(sink)
        except ValueError:
            pass
    # Replace Loguru's default stderr sink once; leave external/test sinks alone.
    try:
        logger.remove(0)
    except ValueError:
        pass
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    common = {
        "format": _FORMAT,
        "colorize": False,
        "backtrace": False,
        "diagnose": False,
    }
    _sinks = [
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=console_format,
            colorize=settings.log_colorize and "NO_COLOR" not in os.environ,
            backtrace=False,
            diagnose=False,
        ),
        logger.add(
            settings.log_dir / "hireagent.log",
            level=settings.log_level,
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            encoding="utf-8",
            **common,
        ),
        logger.add(
            settings.log_dir / "errors.log",
            level="ERROR",
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            encoding="utf-8",
            **common,
        ),
    ]
    handler = InterceptHandler()
    logging.basicConfig(handlers=[handler], level=settings.log_level, force=True)
    for name in ("uvicorn", "uvicorn.error"):
        standard = logging.getLogger(name)
        standard.handlers = [handler]
        standard.propagate = False
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("httpx", "httpcore", "sqlalchemy"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logger.info("logging.ready")


def summary(output):
    if not isinstance(output, dict):
        return {}
    fields = {}
    screening = output.get("screening", {})
    if screening:
        fields["hard_result"] = screening.get("result")
        fields["conditions"] = [
            {
                "id": c.get("condition_id"),
                "result": c.get("result"),
                "basis": c.get("basis"),
                "evidence_count": len(c.get("evidence_ids", [])),
            }
            for c in screening.get("hard_conditions", [])
        ]
    evaluation = output.get("evaluation", {})
    if evaluation.get("dimension_scores"):
        fields["scores"] = [
            {
                "id": d.get("dimension_id"),
                "score": d.get("score"),
                "matched": d.get("matched"),
            }
            for d in evaluation["dimension_scores"]
        ]
    if "scoring_matches" in output:
        fields["matches"] = [
            {
                "id": m.get("dimension_id"),
                "matched": m.get("matched"),
                "evidence_count": len(m.get("evidence_ids", [])),
            }
            for m in output["scoring_matches"]
        ]
    result = output.get("summary", {})
    fields.update(
        {
            key: result[key]
            for key in ("total_score", "recommendation", "needs_human_review")
            if key in result
        }
    )
    if "pages" in output:
        fields["document_chars"] = sum(len(p.get("text", "")) for p in output["pages"])
    if "analysis" in output:
        fields["evidence_count"] = len(output["analysis"].get("evidence", []))
    if output.get("decision") in ("approve", "defer"):
        fields["decision"] = output["decision"]
    return fields


def traced(event, *, agent=None, node_arg=None, state_arg=None, id_arg=None):
    """Async task-local correlation inherited by nested model calls."""

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        async def wrapped(*args, **kwargs):
            bound = signature.bind(*args, **kwargs).arguments
            fields = {"span_id": uuid4().hex[:12]}
            if agent:
                fields["agent"] = agent
            if node_arg:
                fields["node"] = bound[node_arg]
            if id_arg:
                fields["task_id" if id_arg == "tid" else id_arg] = bound[id_arg]
            if state_arg:
                state = bound[state_arg]
                fields.update(
                    {
                        key: state[key]
                        for key in ("candidate_id", "task_id", "file_id")
                        if key in state
                    }
                )
            if fields.get("node") == "auto_approve":
                fields["agent"] = "interview"
            started = perf_counter()
            with logger.contextualize(**fields):
                logger.info("{}.started", event)
                try:
                    output = await function(*args, **kwargs)
                except asyncio.CancelledError:
                    logger.bind(
                        duration_ms=round((perf_counter() - started) * 1000, 2)
                    ).warning("{}.cancelled", event)
                    raise
                except Exception as exc:
                    if type(exc).__name__ in ("GraphInterrupt", "NodeInterrupt"):
                        logger.info("{}.waiting_for_human", event)
                    else:
                        logger.bind(
                            **error_fields(exc),
                            duration_ms=round((perf_counter() - started) * 1000, 2),
                        ).error("{}.failed", event)
                    raise
                log = logger.bind(
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    result=summary(output),
                )
                if (
                    isinstance(output, dict)
                    and output.get("execution_status") == "failed"
                ):
                    log.error(f"{event}.failed")
                else:
                    log.info(f"{event}.completed")
                return output

        return wrapped

    return decorate
