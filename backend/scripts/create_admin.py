"""Run manually: uv run python -m scripts.create_admin (requires 08-auth-rbac.sql)."""

import asyncio
from getpass import getpass

from sqlalchemy import select

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings
from app.models.mysql.entities import AuthRole, AuthUser
from app.services.auth_service import hash_password


async def create(username, display_name, password):
    db = MySQLClient(Settings())
    try:
        async with db.session() as session:
            role = await session.scalar(
                select(AuthRole).where(AuthRole.code == "admin").with_for_update()
            )
            if not role:
                raise ValueError("请先执行 08-auth-rbac.sql")
            if await session.scalar(
                select(AuthUser.id)
                .where(AuthUser.role_id == role.id, AuthUser.status == "active")
                .limit(1)
            ):
                raise ValueError("已有有效管理员，请通过用户管理创建账号")
            import re

            if (
                not re.fullmatch(r"[a-z0-9_.-]{3,64}", username)
                or not display_name
                or len(display_name) > 128
            ):
                raise ValueError("用户名须为 3–64 位字母数字或 _.-；姓名须为 1–128 字")
            if not 1 <= len(password) <= 128:
                raise ValueError("密码长度须为 1–128 位")
            session.add(
                AuthUser(
                    username=username,
                    display_name=display_name,
                    password_hash=await hash_password(password),
                    role_id=role.id,
                    must_change_password=False,
                )
            )
    finally:
        await db.close()


if __name__ == "__main__":
    username = input("管理员用户名：").strip().lower()
    display_name = input("显示姓名：").strip()
    password = getpass("密码（1–128 位）：")
    if password != getpass("再次输入密码："):
        raise SystemExit("两次密码不一致")
    try:
        asyncio.run(create(username, display_name, password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:  # noqa: BLE001 - CLI boundary must not expose connection secrets
        raise SystemExit(
            "初始化失败，请检查连接、表结构及用户名；未输出驱动细节"
        ) from None
    print("管理员已创建，可登录。")
