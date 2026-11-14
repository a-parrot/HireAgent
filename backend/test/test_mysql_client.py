"""手动测试真实 MySQL：uv run python test/test_mysql_client.py。"""

import asyncio
import sys
from pathlib import Path

import pytest

# 支持直接执行脚本；默认 pytest 收集时不会访问数据库。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import SQLAlchemyError

from app.clients.mysql_client import MySQLClient
from app.core.config import Settings
from test.live_checks import require_live_check


async def check_mysql() -> int:
    try:
        config = Settings()
    except ValueError:
        print("[失败] .env 配置格式不正确，请检查数据库配置。")
        return 1

    print(f"连接 MySQL：{config.db_host}:{config.db_port}/{config.db_name}")
    client = MySQLClient(config)
    try:
        await client.ping()
        print("[通过] MySQL 连接成功，SELECT 1 执行成功；未修改任何数据。")
        return 0
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        original = getattr(exc, "orig", exc)
        args = getattr(original, "args", ())
        code = args[0] if args and isinstance(args[0], int) else type(original).__name__
        print(f"[失败] MySQL 无法连接，错误代码：{code}。")
        print("请检查 DB_HOST、DB_PORT、账号密码、数据库名称和服务器访问规则。")
        return 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_mysql_connection(request, capsys):
    require_live_check(request, __file__, "RUN_MYSQL_TESTS")
    with capsys.disabled():
        code = await check_mysql()
    assert code == 0, "MySQL 测试失败，请查看上方的连接错误提示"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check_mysql()))
