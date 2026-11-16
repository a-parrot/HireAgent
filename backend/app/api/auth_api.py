import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy import select

from app.core.errors import BusinessError
from app.models.mysql.entities import AuthRole, AuthUser
from app.services import auth_service as auth

router = APIRouter(prefix="/api/auth", tags=["登录与用户"])


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)


class PasswordInput(BaseModel):
    old_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=1, max_length=128)


class UserInput(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=128)
    role_id: int = Field(gt=0)

    @field_validator("display_name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("姓名不能为空")
        return value.strip()


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    role_id: int | None = Field(default=None, gt=0)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    password: SecretStr | None = Field(default=None, min_length=1, max_length=128)


def cookies(response, request, token, csrf):
    opts = {
        "secure": request.app.state.settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": request.app.state.settings.auth_session_hours * 3600,
    }
    response.set_cookie(auth.COOKIE, token, httponly=True, **opts)
    response.set_cookie("hireagent_csrf", csrf, httponly=False, **opts)
    response.headers["Cache-Control"] = "no-store"


def clear_cookies(response):
    response.delete_cookie(auth.COOKIE, path="/")
    response.delete_cookie("hireagent_csrf", path="/")
    response.headers["Cache-Control"] = "no-store"


async def current(request: Request):
    return await auth.authenticate(request)


async def administrator(request: Request, actor: Annotated[dict, Depends(current)]):
    if actor["must_change_password"]:
        raise BusinessError("请先修改初始密码", 403)
    if "users.manage" not in actor["permissions"]:
        raise BusinessError("没有用户管理权限", 403)
    return actor


@router.post("/login")
async def login(request: Request, response: Response, data: LoginInput):
    auth.check_origin(request)
    limits = getattr(request.app.state, "login_limits", None)
    if limits is None:
        limits = request.app.state.login_limits = defaultdict(deque)
    now = time.monotonic()
    key = request.client.host if request.client else "unknown"
    # Bound memory; expired sources can be discarded without trusting forwarding headers.
    if len(limits) >= 10000:
        for ip in list(limits):
            if not limits[ip] or limits[ip][-1] < now - 60:
                del limits[ip]
        if len(limits) >= 10000 and key not in limits:
            raise BusinessError("登录请求过多，请稍后重试", 429)
    queue = limits[key]
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= 30:
        raise BusinessError("登录请求过多，请稍后重试", 429)
    queue.append(now)
    actor, token, csrf = await auth.login(
        request.app.state.mysql,
        request.app.state.settings,
        data.username,
        data.password.get_secret_value(),
    )
    # Replace an existing session on explicit login; do not keep stale tokens live.
    old = request.cookies.get(auth.COOKIE)
    if old:
        from sqlalchemy import update

        from app.models.mysql.entities import AuthSession, utcnow

        async with request.app.state.mysql.session() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.token_hash == auth.digest(old))
                .values(revoked_at=utcnow())
            )
    cookies(response, request, token, csrf)
    return actor


@router.get("/me")
async def me(response: Response, actor: Annotated[dict, Depends(current)]):
    response.headers["Cache-Control"] = "no-store"
    return {k: v for k, v in actor.items() if k != "session_id"}


@router.post("/logout")
async def logout(
    request: Request, response: Response, actor: Annotated[dict, Depends(current)]
):
    await auth.revoke(request.app.state.mysql, session_id=actor["session_id"])
    clear_cookies(response)
    return {"detail": "已退出登录"}


@router.post("/change-password")
async def password(
    request: Request,
    response: Response,
    data: PasswordInput,
    actor: Annotated[dict, Depends(current)],
):
    await auth.change_password(
        request.app.state.mysql,
        actor,
        data.old_password.get_secret_value(),
        data.new_password.get_secret_value(),
    )
    clear_cookies(response)
    return {"detail": "密码已修改，请重新登录"}


@router.get("/roles")
async def roles(request: Request, actor: Annotated[dict, Depends(administrator)]):
    async with request.app.state.mysql.session() as session:
        return {
            "items": [
                {"id": str(r.id), "code": r.code, "name": r.name}
                for r in await session.scalars(select(AuthRole).order_by(AuthRole.id))
            ]
        }


@router.get("/users")
async def users(request: Request, actor: Annotated[dict, Depends(administrator)]):
    async with request.app.state.mysql.session() as session:
        return {
            "items": [
                await auth.identity(session, u)
                for u in await session.scalars(select(AuthUser).order_by(AuthUser.id))
            ]
        }


@router.post("/users", status_code=201)
async def create_user(
    request: Request, data: UserInput, actor: Annotated[dict, Depends(administrator)]
):
    values = data.model_dump()
    values["password"] = data.password.get_secret_value()
    return await auth.manage_user(request.app.state.mysql, actor, None, values)


@router.patch("/users/{user_id}")
async def edit_user(
    request: Request,
    user_id: int,
    data: UserPatch,
    actor: Annotated[dict, Depends(administrator)],
):
    values = data.model_dump(exclude_none=True)
    if data.password:
        values["password"] = data.password.get_secret_value()
    if "display_name" in values:
        values["display_name"] = values["display_name"].strip()
        if not values["display_name"]:
            raise BusinessError("姓名不能为空")
    return await auth.manage_user(request.app.state.mysql, actor, user_id, values)


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_user(
    request: Request, user_id: int, actor: Annotated[dict, Depends(administrator)]
):
    await auth.revoke(request.app.state.mysql, user_id=user_id)
    return {"detail": "该用户的登录会话已吊销"}
