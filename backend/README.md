# HireAgent 后端

Python 3.12、uv、FastAPI、SQLAlchemy 异步引擎及 aiomysql。

## 配置与启动

在 backend 目录执行：

```bash
uv sync
cp .env.example .env
# 修改 .env，填写实际数据库地址和应用账号密码
uv run python main.py
```

Windows PowerShell 使用 `Copy-Item .env.example .env`。配置文件始终从 backend/.env 加载，环境变量优先；不要提交实际凭证。

默认地址 http://127.0.0.1:8000，接口文档 http://127.0.0.1:8000/docs。
开发热更新可使用 `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`，此时监听地址与端口以命令参数为准。

- Ubuntu 宿主机后端连接 Docker MySQL：DB_HOST=127.0.0.1、DB_PORT=3306。
- Windows 后端经 SSH 隧道连接：DB_HOST=127.0.0.1、DB_PORT=13306。
- 后端与 MySQL 位于同一 Compose 网络时：DB_HOST=mysql、DB_PORT=3306。
- `GET /api/health`：进程存活；`GET /api/health/ready`：实时检查数据库，不可用返回 503。

启动时执行 SELECT 1，连接失败则停止启动并释放连接池。每次数据库操作通过 MySQLClient.session() 获取独立事务，成功提交、异常回滚并关闭；不要跨任务共享 Session。模型或外部请求期间不持有数据库事务。

当前只实现基础架构，不自动建业务表，不初始化 LangGraph 检查点，也不提供尚未实现的业务接口。后续业务表通过 Alembic 迁移。

## 验证

```bash
uv run pytest
uv run ruff check app main.py test
```

默认测试使用隔离替身验证应用生命周期，不连接外部数据库。配置好 .env 后，在 Ubuntu 执行只读真实连接测试：

```bash
RUN_MYSQL_TESTS=1 uv run pytest test/integration/test_mysql.py
```

Windows PowerShell 先执行 `$env:RUN_MYSQL_TESTS="1"`，再运行同一 pytest 命令。
