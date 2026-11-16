from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.api.authorization import permission
from app.main import create_app
from app.models.mysql.entities import (
    AuthPermission,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    utcnow,
)
from app.services.auth_service import hash_password
from test.integration.test_business import config

pytestmark = [pytest.mark.asyncio, pytest.mark.auth]
PASSWORD = "Testing-Password-123!"


async def client_for(db, tmp_path):
    async with db.session() as s:
        roles = [
            AuthRole(code=code, name=code) for code in ("admin", "recruiter", "viewer")
        ]
        s.add_all(roles)
        await s.flush()
        perms = [
            AuthPermission(code=code, name=code)
            for code in (
                "users.manage",
                "jobs.read",
                "jobs.write",
                "resumes.read",
                "resumes.write",
                "evaluations.read",
                "evaluations.run",
                "evaluations.review",
                "evaluations.delete",
                "schedules.read",
                "schedules.write",
                "actions.execute",
                "history.read",
            )
        ]
        s.add_all(perms)
        await s.flush()
        for role in roles:
            for p in perms:
                if (
                    role.code == "admin"
                    or (role.code == "viewer" and p.code.endswith(".read"))
                    or (role.code == "recruiter" and p.code != "users.manage")
                ):
                    s.add(AuthRolePermission(role_id=role.id, permission_id=p.id))
            s.add(
                AuthUser(
                    username=role.code,
                    display_name=role.code,
                    role_id=role.id,
                    password_hash=await hash_password(PASSWORD),
                    must_change_password=False,
                )
            )
    app = create_app(config(tmp_path))
    app.state.mysql = db
    app.state.runtime = None
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ), app


async def sign_in(client, username="admin"):
    response = await client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies["hireagent_csrf"]
    return response


async def test_all_business_endpoints_protected_and_viewer_cannot_write(db, tmp_path):
    client, app = await client_for(db, tmp_path)
    async with client:
        for path in (
            "/api/jobs",
            "/api/files/1",
            "/api/files/1/content",
            "/api/candidates/1/export",
            "/api/history/imports",
        ):
            assert (await client.get(path)).status_code == 401
        await sign_in(client, "viewer")
        assert (await client.get("/api/jobs")).status_code == 200
        for path, body in [
            ("/api/jobs", {"name": "blocked"}),
            ("/api/candidates/1/retry", {}),
            ("/api/evaluations/auto-schedule", {}),
            ("/api/auth/users", {}),
        ]:
            assert (await client.post(path, json=body)).status_code == 403
        for route in app.routes:
            if (
                hasattr(route, "methods")
                and route.path.startswith("/api/")
                and not route.path.startswith(("/api/health", "/api/auth"))
            ):
                assert all(permission(route.path, m) for m in route.methods)
        assert (await client.get("/docs")).status_code == 404


async def test_csrf_origin_logout_and_password_change(db, tmp_path):
    client, _ = await client_for(db, tmp_path)
    async with client:
        response = await sign_in(client)
        assert "httponly" in response.headers.get_list("set-cookie")[0].lower()
        csrf = client.headers.pop("X-CSRF-Token")
        assert (await client.post("/api/auth/logout")).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert (
            await client.post(
                "/api/auth/logout", headers={"origin": "https://attacker.invalid"}
            )
        ).status_code == 403
        result = await client.post(
            "/api/auth/change-password",
            json={
                "old_password": PASSWORD,
                "new_password": "a",
            },
        )
        assert result.status_code == 200
        assert (await client.get("/api/auth/me")).status_code == 401
        assert (
            await client.post(
                "/api/auth/login", json={"username": "admin", "password": PASSWORD}
            )
        ).status_code == 401
        assert (
            await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "a"},
            )
        ).status_code == 200
        client.headers["X-CSRF-Token"] = client.cookies["hireagent_csrf"]
        assert (await client.post("/api/auth/logout")).status_code == 200
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_lockout_failure_persists_and_session_expiry(db, tmp_path):
    client, _ = await client_for(db, tmp_path)
    async with client:
        for _ in range(5):
            assert (
                await client.post(
                    "/api/auth/login", json={"username": "admin", "password": "wrong"}
                )
            ).status_code == 401
        assert (
            await client.post(
                "/api/auth/login", json={"username": "admin", "password": PASSWORD}
            )
        ).status_code == 401
        async with db.session() as s:
            user = await s.scalar(select(AuthUser).where(AuthUser.username == "admin"))
            assert user.failed_login_attempts == 5 and user.locked_until > utcnow()
            user.locked_until = utcnow() - timedelta(minutes=1)
        # A second burst after lock expiry must start a new lockout window.
        for _ in range(5):
            assert (
                await client.post(
                    "/api/auth/login", json={"username": "admin", "password": "wrong"}
                )
            ).status_code == 401
        async with db.session() as s:
            user = await s.scalar(select(AuthUser).where(AuthUser.username == "admin"))
            assert user.failed_login_attempts == 5 and user.locked_until > utcnow()
            user.locked_until = utcnow() - timedelta(minutes=1)
        await sign_in(client)
        async with db.session() as s:
            entry = await s.scalar(select(AuthSession))
            entry.last_seen_at = utcnow() - timedelta(hours=1)
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_admin_create_first_password_gate_disable_and_last_admin_protection(
    db, tmp_path
):
    client, _ = await client_for(db, tmp_path)
    async with client:
        admin = (await sign_in(client)).json()
        roles = (await client.get("/api/auth/roles")).json()["items"]
        viewer = next(r for r in roles if r["code"] == "viewer")
        created = await client.post(
            "/api/auth/users",
            json={
                "username": "newuser",
                "display_name": "新用户",
                "role_id": int(viewer["id"]),
                "password": PASSWORD,
            },
        )
        assert created.status_code == 201
        uid = created.json()["id"]
        assert "password_hash" not in created.json()
        assert (
            await client.patch(
                f"/api/auth/users/{admin['id']}", json={"status": "disabled"}
            )
        ).status_code == 409
        # Independent browser for the new account.
        async with httpx.AsyncClient(
            transport=client._transport, base_url="http://test"
        ) as other:
            await sign_in(other, "newuser")
            assert (await other.get("/api/jobs")).status_code == 403
            assert (await other.get("/api/auth/me")).json()["must_change_password"]
            assert (
                await client.patch(
                    f"/api/auth/users/{uid}", json={"status": "disabled"}
                )
            ).status_code == 200
            assert (await other.get("/api/auth/me")).status_code == 401


async def test_operator_name_is_server_owned_and_validation_never_echoes_password(
    db, tmp_path, monkeypatch
):
    from unittest.mock import AsyncMock

    import app.api.review_api.review_router as review_module

    review = AsyncMock(return_value={"id": "1", "resume_status": "pending"})
    monkeypatch.setattr(review_module, "review_candidate", review)
    client, _ = await client_for(db, tmp_path)
    async with client:
        await sign_in(client)
        result = await client.post(
            "/api/candidates/1/review",
            json={
                "operation": "approve",
                "review_version": 0,
                "reason": "verified",
                "operator_name": "forged user",
            },
        )
        assert result.status_code == 200
        assert review.await_args.args[3].operator_name == "admin"
        rejected = await client.post(
            "/api/auth/users",
            json={
                "username": "abc",
                "display_name": "abc",
                "role_id": 1,
                "password": "secretshort" * 13,
            },
        )
        assert rejected.status_code == 422
        assert "secretshort" not in rejected.text


async def test_recruiter_cannot_manage_users_and_explicit_revoke_is_immediate(
    db, tmp_path
):
    client, _ = await client_for(db, tmp_path)
    async with client:
        recruiter = (await sign_in(client, "recruiter")).json()
        assert (await client.get("/api/auth/users")).status_code == 403
        async with httpx.AsyncClient(
            transport=client._transport, base_url="http://test"
        ) as administrator:
            await sign_in(administrator)
            result = await administrator.post(
                f"/api/auth/users/{recruiter['id']}/revoke-sessions"
            )
            assert result.status_code == 200
        assert (await client.get("/api/auth/me")).status_code == 401
