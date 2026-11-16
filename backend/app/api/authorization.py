"""A permission for every business endpoint; authentication cannot be bypassed by UI."""

from contextvars import ContextVar

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.errors import BusinessError
from app.models.mysql.entities import Event
from app.services.auth_service import authenticate

actor_context = ContextVar("actor", default=None)


@event.listens_for(Session, "before_flush")
def stamp_events(session, context, instances):
    actor = actor_context.get()
    if actor:
        for item in session.new:
            if isinstance(item, Event):
                item.details = {
                    **(item.details or {}),
                    "actor_user_id": actor["id"],
                    "actor_username": actor["username"],
                    "actor_display_name": actor["display_name"],
                }


def permission(path, method):
    read = method in ("GET", "HEAD")
    if "/action-preview" in path or any(
        s in path for s in ("/approve-actions", "/retry-actions", "/reconcile-actions")
    ):
        return "actions.execute"
    if path.startswith("/api/history") or path.endswith("/events"):
        return "history.read"
    if path.startswith("/api/files"):
        return "resumes.read" if read else None
    if "/resumes" in path or path == "/api/resume-workspace/jobs":
        return "resumes.read" if read else "resumes.write"
    if path.endswith("/review"):
        return "evaluations.review"
    if path.endswith("/auto-schedule"):
        return "schedules.write"
    if any(s in path for s in ("/slots", "/schedule", "/interviews", "/reservations")):
        return "schedules.read" if read else "schedules.write"
    if path.startswith("/api/jobs") and not path.endswith("/evaluate"):
        return "jobs.read" if read else "jobs.write"
    if path.startswith("/api/evaluations"):
        return "evaluations.read" if read else "evaluations.delete"
    if path.startswith(("/api/candidates", "/api/batches")) or path.endswith(
        "/evaluate"
    ):
        return "evaluations.read" if read else "evaluations.run"
    return None


async def authorize(request: Request):
    actor = await authenticate(request)
    if actor["must_change_password"]:
        raise BusinessError("请先修改初始密码", 403)
    required = permission(request.scope["route"].path, request.method)
    if not required or required not in actor["permissions"]:
        raise BusinessError("无权执行此操作", 403)
    if (
        request.method == "POST"
        and request.scope["route"].path == "/api/jobs/{job_id}/resumes"
    ):
        form = await request.form()
        if (
            str(form.get("auto_evaluate", "")).lower() in ("true", "1")
            and "evaluations.run" not in actor["permissions"]
        ):
            raise BusinessError("没有执行评估权限", 403)
    token = actor_context.set(actor)
    try:
        yield actor
    finally:
        actor_context.reset(token)


def operator_data(request, data):
    actor = getattr(request.state, "actor", None)
    return (
        data.model_copy(update={"operator_name": actor["display_name"]})
        if actor
        else data
    )
