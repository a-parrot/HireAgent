# HireAgent 后端

Python 3.12 + uv + FastAPI + MySQL 8.4 + LangGraph。MySQL 驱动已包含 RSA 认证依赖，支持 MySQL 8 默认密码认证。当前已实现岗位版本、文件与批次、三智能体流程、人工审核、批量恢复、排期候补及完整导出。会议/通知目前仅完成授权与幂等编排，具体平台适配器待用户选定后实现，不代表真实服务已接入。前端暂未开发。

## 1. 环境与数据库

在 backend 目录执行，先配置独立的 MySQL 数据库及应用账号。MySQL Compose 在 ../docker-ubuntu 中。

```bash
uv sync
# 仅在没有 .env 时复制；已有配置不要覆盖
cp .env.example .env
```

Windows 首次复制使用 `Copy-Item .env.example .env`。编辑 .env，配置 DB_HOST、DB_PORT、DB_NAME、DB_USER、DB_PASSWORD。Ubuntu 宿主机连接 Docker MySQL 使用 127.0.0.1:3306；Windows 经 SSH 隧道可使用 127.0.0.1:13306；同 Compose 网络中的应用使用 mysql:3306。不要复制参考项目的知识库数据库连接来运行本项目迁移。

当前本地 .env 已从用户指定参考项目导入百炼模型配置，不含参考项目其他数据库或存储凭证，且被 Git 忽略。连通性测试返回 HTTP 403 / AccessDenied.Unpurchased；需用户开通所配置模型或在 .env 指定可用模型，尚未完成真实模型验收。

## 2. 初始化（选择一种数据库入口）

### 新的空数据库

```bash
uv run alembic upgrade head
uv run python -m scripts.seed_job
uv run python -m scripts.init_checkpoints
uv run python main.py
```

五个 Alembic revision 依次建立岗位、简历、审核、执行、排期/动作表；SQL 固化在 revision 内，不随以后 ORM 修改而改变历史迁移。初始岗位导入可重复执行，不覆盖已有配置。数据库名必须预先存在，迁移不创建账号、不修改密码。不要在有用户数据的数据库执行 downgrade。

### 已导入 sql/01-schema.sql 的数据库

不要再无条件执行建表迁移。先运行 `uv run python -m scripts.verify_schema`，并人工核对 sql/01-schema.sql 的 CHECK、默认值及索引；只有确认完整 12 表与本仓库 revision 005 一致时，才执行 `uv run alembic stamp 005`。有结构差异或只有部分表时应先编写增量迁移对齐。检查点表仍由适配器 setup 创建，与业务表版本独立。

## 3. 启动与配置

应用默认 http://127.0.0.1:8000；Swagger 在 /docs，OpenAPI 在 /openapi.json。

```bash
uv run python main.py
# 或本地开发热更新（只使用单 worker）
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

环境配置始终从 backend/.env 加载，进程环境变量优先。监听参数 APP_HOST/APP_PORT 用于 main.py；uvicorn 命令行启动时以命令行参数为准。需要外部访问时按实际部署设置监听地址与防火墙。当前按需求没有账号权限系统，应在受控网络使用，不能当成带鉴权的公网招聘服务。

启动时检查 MySQL、业务表和单实例命名锁，初始化 MySQL 检查点，恢复已启动但未完成的候选人；人工暂停者保持暂停。缺少迁移时启动失败，不自动建业务表或回退到 SQLite。退出会取消后台任务并释放模型连接、检查点、锁和数据库连接池。进程异常停止后重启继续，不能多 worker 同时运行。

- `GET /api/health`：进程存活。
- `GET /api/health/ready`：数据库实时就绪，不可用返回 503。
- 模型使用 OpenAI 兼容 chat/completions 协议；百炼配置 `LLM_PROVIDER=dashscope`，JSON 输出禁用 thinking。BASE_URL 填写兼容 API 根路径，不含 /chat/completions。
- 模型未配置或调用失败时记录候选人失败，不回退固定分数；模型超时/限流最多重试两次。
- 文件和逐页文本位于 backend/storage，运行产物被 Git 忽略。默认并发为 3，每份 PDF 上限 20MB，每批最多 250 份；生产批次使用真实上传，不填充演示数据。

## 4. 业务操作顺序

1. 新建岗位草稿，编辑规则，发布；或使用初始化岗位 v1。发布需要当前 draft_version，每次发布会推进草稿版本。
2. 创建批次，上传 PDF，指定岗位及发布版本。批次复制不可变规则快照，同批次重复文件按哈希去重。
3. 启动批次，轮询进度与事件。顺序执行 parse_pdf → analyze_resume → evaluate_candidate → review_evaluation → summarize_result。
4. 推荐或需要复核者等待人工操作。通过 review_version 提交补充、批准或暂缓；补充需 description/source，不自动批准。批准后按原 thread_id 恢复，不重复成功节点。
5. 评估稳定后配置四个互不重叠的实际 45 分钟时段，为有效批准者统一排序排期。时间必须携带时区偏移；满额/冲突候补，后批准者不挤出已有预约。
6. 为预约填写并确认收件人与通知预览，批准指定 preview_version 才能执行外部动作。未选平台保持 not_configured；会议成功才通知，通知失败只重试通知。超时或运行中崩溃保持 uncertain，先查询核实，不盲目重发。
7. 查看候选人、日志和排期结果，导出 JSON 或 CSV。评估完成、人工批准、预约成功、会议成功和通知成功是不同状态。

ID 在响应中为字符串；时间字段为 UTC ISO 8601，时段另带 IANA 时区。详细契约见 ../docs/api/后端接口说明.md。

## 5. 验证与限制

```bash
uv run pytest
uv run ruff check app main.py test scripts alembic
uv run ruff format --check app main.py test scripts alembic
uv run alembic upgrade head --sql
```

默认集成测试使用临时 SQLite、真实 SQLAlchemy/LangGraph 和生成的测试 PDF，模型与外部服务使用隔离替身。SQLite 仅存在于测试，不是业务运行后端；这些测试不能替代 MySQL 锁、CHECK 和检查点适配器验收。

只读连接验证：`RUN_MYSQL_TESTS=1 uv run pytest test/integration/test_mysql.py`。

真实 MySQL 迁移与持久检查点测试必须先由用户创建专用的 *_test 数据库；设置 DB_NAME 为该库后执行：

```bash
RUN_MYSQL_BACKEND_TESTS=1 uv run pytest test/integration/test_mysql_backend.py
```

该测试会建表并写入测试数据，不清空数据库；模型仅使用测试替身，不会发送真实简历。Windows PowerShell 通过 `$env:变量名="值"` 设置开关。

真实简历会发送至外部模型。仅在用户明确授权发送该简历到选定平台后，才执行：

```bash
uv run python -m scripts.smoke_model --pdf /实际路径/简历.pdf
```

输出保存在被忽略的 storage/exports/model-smoke.json，包含个人数据，不提交。用户已选择暂不发送真实简历，尚未执行此验证；后续需要重新明确授权，不能因为模型可用就自行发送。

## 6. 部署与备份

Ubuntu 顺序：启动 MySQL → 配置 .env → uv sync → 业务迁移/结构对齐 → 初始规则及检查点初始化 → 启动单后端。所有外部服务凭证只在环境变量或本地配置中维护。

备份时停止业务写入，使用数据库备份工具导出业务表、alembic_version 与检查点表，同时备份 storage/uploads、storage/page_texts。先在独立环境恢复并核对文件路径/页码、待人工任务和外部动作记录，再用于服务恢复。MySQL 命名卷不是备份，不使用 down -v 删除需要保留的数据。

会议与通知仍缺平台名称和凭证，当前不伪造真实 ID、不发送任何消息；完整后端验收与 Ubuntu 实测状态见 ../docs/prompts/验收记录.md。

## 7. Ubuntu 可选后端容器

原有单文件 dockercompose.yaml 保留 MySQL 配置，新增 backend profile；普通 up -d 仍只启动 MySQL。先在 backend/.env 填好模型等配置，数据库地址和账号由 Compose 内的 MySQL 配置复用，不在镜像中复制 .env。前端尚未容器化。

在 docker-ubuntu 目录操作：

```bash
docker compose -f dockercompose.yaml up -d mysql
docker compose -f dockercompose.yaml --profile backend build backend
# 仅新空库执行下面的建表迁移；已导 SQL 库按前述结构核对/接管流程操作
docker compose -f dockercompose.yaml --profile backend run --rm backend alembic upgrade head
docker compose -f dockercompose.yaml --profile backend run --rm backend python -m scripts.seed_job
docker compose -f dockercompose.yaml --profile backend run --rm backend python -m scripts.init_checkpoints
docker compose -f dockercompose.yaml --profile backend up -d backend
docker compose -f dockercompose.yaml --profile backend logs --tail=100 backend
```

后端默认映射 Ubuntu 本机 127.0.0.1:8000。需要 Windows 本地调试时可建立 SSH 隧道 `ssh -N -L 8000:127.0.0.1:8000 用户@服务器`；随后访问本地 /docs。应用文件位于独立 backend_storage 命名卷，备份时也要导出该卷中的上传原件和页文本。该命名卷不会自动导入宿主机已有 backend/storage 文件；已有原件应在停写期间手动迁移并核对。

Dockerfile 使用 uv.lock 同步生产依赖，不包含测试依赖。当前只通过 Compose 配置验证，尚未在运行中的 Docker Engine 构建或启动后端镜像。
