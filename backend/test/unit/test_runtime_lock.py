from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.workflow_service.runtime import WorkflowRuntime


def runtime_with_connection(results):
    connection = AsyncMock()
    connection.scalar.side_effect = results

    @asynccontextmanager
    async def connect():
        yield connection

    db = SimpleNamespace(engine=SimpleNamespace(connect=connect))
    config = Settings(_env_file=None, startup_lock_wait_seconds=10)
    return WorkflowRuntime(db, config), connection


@pytest.mark.asyncio
async def test_lock_handoff_waits_and_discards_connection_on_shutdown():
    runtime, connection = runtime_with_connection([1])
    try:
        await runtime.acquire_runtime_lock()
        assert connection.scalar.await_args.args[1]["wait"] == 10
        assert runtime.runtime_connection is connection
    finally:
        await runtime.close()
    await runtime.close()
    assert connection.execute.await_count == 2
    assert "SET SESSION wait_timeout" in str(
        connection.execute.await_args_list[0].args[0]
    )
    assert "RELEASE_LOCK" in str(connection.execute.await_args_list[1].args[0])
    connection.invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_conflict_reports_owner_and_never_releases_another_instance_lock():
    runtime, connection = runtime_with_connection([0, 2312])
    try:
        with pytest.raises(RuntimeError, match="连接 ID：2312"):
            await runtime.acquire_runtime_lock()
    finally:
        await runtime.close()
    assert all(
        "RELEASE_LOCK" not in str(call.args[0])
        for call in connection.execute.await_args_list
    )
    connection.invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_null_lock_result_is_not_misreported_as_another_instance():
    runtime, connection = runtime_with_connection([None])
    try:
        with pytest.raises(RuntimeError, match="锁获取失败"):
            await runtime.acquire_runtime_lock()
    finally:
        await runtime.close()
    connection.invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_unlock_error_still_discards_the_physical_connection():
    runtime, connection = runtime_with_connection([1])
    await runtime.acquire_runtime_lock()
    connection.execute.side_effect = RuntimeError("unlock failed")
    with pytest.raises(RuntimeError, match="unlock failed"):
        await runtime.close()
    connection.invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_checks_ownership_on_original_connection():
    runtime, connection = runtime_with_connection([1, 1])
    try:
        await runtime.acquire_runtime_lock()
        assert await runtime._heartbeat_once()
        assert "IS_USED_LOCK" in str(connection.scalar.await_args.args[0])
        assert "CONNECTION_ID()" in str(connection.scalar.await_args.args[0])
        assert not runtime.lock_lost
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_loss_fences_enqueues_cancels_tasks_and_suspends_imports():
    import asyncio
    from unittest.mock import Mock

    from app.core.errors import BusinessError

    runtime, connection = runtime_with_connection([1, 0])
    dependent = Mock()
    runtime.on_lock_lost = dependent
    task = asyncio.create_task(asyncio.sleep(100))
    runtime.tasks[1] = task
    try:
        await runtime.acquire_runtime_lock()
        assert not await runtime._heartbeat_once()
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled() and runtime.lock_lost
        dependent.assert_called_once()
        with pytest.raises(BusinessError, match="锁已失效"):
            runtime.enqueue(2)
        assert 2 not in runtime.tasks
        assert not await runtime._heartbeat_once()
        dependent.assert_called_once()
    finally:
        await runtime.close()
    assert all(
        "RELEASE_LOCK" not in str(call.args[0])
        for call in connection.execute.await_args_list
    )


@pytest.mark.asyncio
async def test_connection_error_fails_closed_without_reacquiring_lock():
    runtime, connection = runtime_with_connection(
        [1, OSError("private driver details")]
    )
    try:
        await runtime.acquire_runtime_lock()
        assert not await runtime._heartbeat_once()
        assert runtime.lock_lost
        assert connection.scalar.await_count == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_heartbeat_timeout_fails_closed():
    import asyncio

    runtime, connection = runtime_with_connection([1])
    runtime.config.runtime_lock_heartbeat_timeout = 0.01
    try:
        await runtime.acquire_runtime_lock()
        connection.scalar.side_effect = None

        async def stalled(*args, **kwargs):
            await asyncio.sleep(100)

        connection.scalar.side_effect = stalled
        assert not await runtime._heartbeat_once()
        assert runtime.lock_lost
    finally:
        await runtime.close()


def test_invalid_heartbeat_timing_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="心跳间隔"):
        Settings(
            _env_file=None,
            runtime_lock_idle_timeout=15,
            runtime_lock_heartbeat_interval=10,
            runtime_lock_heartbeat_timeout=5,
        )


@pytest.mark.asyncio
async def test_import_scheduler_suspends_and_refuses_new_tasks():
    import asyncio

    from app.core.errors import BusinessError
    from app.services.resume_service.import_runtime import ImportRuntime

    imports = ImportRuntime(None, Settings(_env_file=None))
    task = asyncio.create_task(asyncio.sleep(100))
    imports.tasks[1] = task
    try:
        imports.suspend()
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()
        with pytest.raises(BusinessError, match="解析调度已停止"):
            imports.submit([2])
    finally:
        await imports.close()
