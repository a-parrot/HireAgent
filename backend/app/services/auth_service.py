"""Cookie sessions and role authorization. No plaintext credentials are persisted."""

import asyncio
import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select, update

from app.core.errors import BusinessError
from app.models.mysql.entities import (
    AuthPermission,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    utcnow,
)

PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY = PASSWORDS.hash(secrets.token_urlsafe(32))
HASH_LIMIT = asyncio.Semaphore(4)
COOKIE = "hireagent_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


async def hash_password(value):
    async with HASH_LIMIT:
        return await asyncio.to_thread(PASSWORDS.hash, value)


async def verify_password(encoded, value):
    def verify():
        try:
            return PASSWORDS.verify(encoded, value)
        except (VerificationError, InvalidHashError):
            return False

    async with HASH_LIMIT:
        return await asyncio.to_thread(verify)


async def identity(session, user):
    role = await session.get(AuthRole, user.role_id)
    permissions = list(
        await session.scalars(
            select(AuthPermission.code)
            .join(
                AuthRolePermission,
                AuthRolePermission.permission_id == AuthPermission.id,
            )
            .where(AuthRolePermission.role_id == user.role_id)
        )
    )
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "role": role.code,
        "role_id": str(role.id),
        "role_name": role.name,
        "status": user.status,
        "must_change_password": user.must_change_password,
        "permissions": sorted(permissions),
    }


async def login(db, config, username, password):
    failure = False
    async with db.session() as session:
        user = await session.scalar(
            select(AuthUser)
            .where(AuthUser.username == username.strip().lower())
            .with_for_update()
        )
        valid = await verify_password(user.password_hash if user else DUMMY, password)
        now = utcnow()
        if (
            not user
            or user.status != "active"
            or (user.locked_until and user.locked_until > now)
        ):
            failure = True
        elif not valid:
            if user.locked_until:
                user.failed_login_attempts = 0
                user.locked_until = None
            user.failed_login_attempts = (
                user.failed_login_attempts if not user.locked_until else 0
            ) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
            failure = True
        else:
            user.failed_login_attempts, user.locked_until, user.last_login_at = (
                0,
                None,
                now,
            )
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            session.add(
                AuthSession(
                    user_id=user.id,
                    token_hash=digest(token),
                    csrf_token_hash=digest(csrf),
                    expires_at=now + timedelta(hours=config.auth_session_hours),
                )
            )
            result = await identity(session, user)
    # Raise after committing the failure counters, rather than rolling them back.
    if failure:
        raise BusinessError("用户名或密码错误，或账号暂不可用", 401)
    return result, token, csrf


async def authenticate(request):
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 256:
        raise BusinessError("请先登录", 401)
    async with request.app.state.mysql.session() as session:
        entry = await session.scalar(
            select(AuthSession).where(AuthSession.token_hash == digest(token))
        )
        now = utcnow()
        cfg = request.app.state.settings
        if (
            not entry
            or entry.revoked_at
            or entry.expires_at <= now
            or entry.last_seen_at + timedelta(minutes=cfg.auth_idle_minutes) <= now
        ):
            raise BusinessError("登录已过期，请重新登录", 401)
        user = await session.get(AuthUser, entry.user_id)
        if (
            not user
            or user.status != "active"
            or entry.created_at < user.password_changed_at
        ):
            raise BusinessError("账号或登录已失效", 401)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            csrf = request.headers.get("X-CSRF-Token", "")
            if not secrets.compare_digest(digest(csrf), entry.csrf_token_hash):
                raise BusinessError("请求校验失败，请刷新页面", 403)
            check_origin(request)
        if now - entry.last_seen_at >= timedelta(seconds=60):
            entry.last_seen_at = now
        result = await identity(session, user)
        result["session_id"] = entry.id
        request.state.actor = result
    return result


def check_origin(request):
    origin = request.headers.get("origin")
    allowed = {
        str(request.base_url).rstrip("/"),
        *request.app.state.settings.cors_origins,
    }
    if origin and origin.rstrip("/") not in allowed:
        raise BusinessError("请求来源不允许", 403)


async def revoke(db, user_id=None, session_id=None):
    async with db.session() as session:
        query = update(AuthSession).where(AuthSession.revoked_at.is_(None))
        query = (
            query.where(AuthSession.user_id == user_id)
            if user_id is not None
            else query.where(AuthSession.id == session_id)
        )
        await session.execute(query.values(revoked_at=utcnow()))


async def change_password(db, actor, old, new):
    async with db.session() as session:
        user = await session.scalar(
            select(AuthUser).where(AuthUser.id == int(actor["id"])).with_for_update()
        )
        if not await verify_password(user.password_hash, old):
            raise BusinessError("原密码错误", 400)
        if await verify_password(user.password_hash, new):
            raise BusinessError("新密码不能与原密码相同")
        user.password_hash = await hash_password(new)
        user.password_changed_at = utcnow()
        user.must_change_password = False
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id)
            .values(revoked_at=utcnow())
        )


async def manage_user(db, actor, user_id, data):
    async with db.session() as session:
        # Serializes administrator demotions so concurrent edits cannot remove the last admin.
        roles = (
            await session.scalars(
                select(AuthRole).order_by(AuthRole.id).with_for_update()
            )
        ).all()
        roles_by_id = {r.id: r for r in roles}
        user = (
            await session.scalar(
                select(AuthUser).where(AuthUser.id == user_id).with_for_update()
            )
            if user_id
            else None
        )
        if user_id and not user:
            raise BusinessError("用户不存在", 404)
        role_id = data.get("role_id", user.role_id if user else None)
        if role_id not in roles_by_id:
            raise BusinessError("角色不存在")
        status = data.get("status", user.status if user else "active")
        if (
            user
            and roles_by_id[user.role_id].code == "admin"
            and user.status == "active"
            and (roles_by_id[role_id].code != "admin" or status != "active")
        ):
            admin_ids = [r.id for r in roles if r.code == "admin"]
            other = await session.scalar(
                select(AuthUser.id)
                .where(
                    AuthUser.id != user.id,
                    AuthUser.role_id.in_(admin_ids),
                    AuthUser.status == "active",
                )
                .limit(1)
            )
            if not other:
                raise BusinessError("不能停用或降级最后一位有效管理员", 409)
        if not user:
            user = AuthUser(
                username=data["username"].strip().lower(),
                display_name=data["display_name"],
                role_id=role_id,
            )
            session.add(user)
        user.role_id, user.status = role_id, status
        if "display_name" in data:
            user.display_name = data["display_name"]
        if data.get("password"):
            user.password_hash = await hash_password(data["password"])
            user.password_changed_at, user.must_change_password = utcnow(), True
            user.failed_login_attempts, user.locked_until = 0, None
        await session.flush()
        if user_id:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id)
                .values(revoked_at=utcnow())
            )
        return await identity(session, user)
