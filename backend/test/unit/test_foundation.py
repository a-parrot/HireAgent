from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings
from app.main import create_app


def config():
    return Settings(_env_file=None, db_password=SecretStr("test-only@:/password"))


def test_health_readiness_and_shutdown():
    database = AsyncMock(spec=MySQLClient)
    with (
        patch("app.core.lifespan.MySQLClient", return_value=database),
        patch("app.core.lifespan.WorkflowRuntime", return_value=AsyncMock()),
        TestClient(create_app(config())) as client,
    ):
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/health/ready").status_code == 200
        assert client.get("/openapi.json").status_code == 404
        database.ping.side_effect = SQLAlchemyError("driver detail with secret")
        response = client.get("/api/health/ready")
        assert response.status_code == 503
        assert "secret" not in response.text
        assert client.get("/api/health").status_code == 200
    database.close.assert_awaited_once()


def test_startup_failure_disposes_pool():
    database = AsyncMock(spec=MySQLClient)
    database.ping.side_effect = SQLAlchemyError("private password")
    with (
        patch("app.core.lifespan.MySQLClient", return_value=database),
        patch("app.core.lifespan.WorkflowRuntime", return_value=AsyncMock()),
        pytest.raises(RuntimeError, match="MySQL unavailable") as error,
        TestClient(create_app(config())),
    ):
        pass
    assert "private password" not in str(error.value)
    database.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_password_url_encoding():
    settings = config()
    database = MySQLClient(settings)
    try:
        assert database.engine.url.password == settings.db_password.get_secret_value()
        assert database.engine.url.drivername == "mysql+aiomysql"
        assert settings.db_password.get_secret_value() not in str(database.engine.url)
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_lost_runtime_readiness_and_mutation_fence():
    from types import SimpleNamespace

    import httpx

    app = create_app(config())
    app.state.runtime = SimpleNamespace(lock_lost=True)
    app.state.mysql = AsyncMock(spec=MySQLClient)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/health")).status_code == 200
        assert (await client.get("/api/health/ready")).status_code == 503
        response = await client.post("/api/jobs", json={"name": "must not write"})
        assert response.status_code == 503
        assert "锁已失效" in response.json()["detail"]
        assert (await client.get("/openapi.json")).status_code == 404
    app.state.mysql.ping.assert_not_awaited()
