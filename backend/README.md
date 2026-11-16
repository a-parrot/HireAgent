# HireAgent 后端

当前“已批准自动排期”不再以推荐分数线限制人工批准记录：人工批准面试后，即使原始分数为 40/60 分、原 AI 结论仍为需复核或不推荐，也可按总分降序自动安排。同分继续按岗位配置的排名优先级及候选人 ID 排列。填写起始时间后每人生成 45 分钟；已有预约保留且幂等。不再等待同批其他简历完成，也不等待已保存人工决定的工作流恢复锁。未批准的存疑结果仍不自动放行；原有评分达标且证据完整的自动准入规则保留。


当前批量处理：IMPORT_CONCURRENCY=1、MODEL_CONCURRENCY=1，解析和评估各自逐份串行。简历工作区新增“查看正在评估”“查看正在解析”与独立评估状态筛选，筛选在服务器分页前执行，长文节点显示“第 x/y 段”。更新配置需重启后端，旧评估队列按已有检查点恢复，无需重新导入整批简历。


## 登录与权限（当前已启用）

所有招聘业务接口、简历原件/预览、导出和日志均须登录。默认三类角色：管理员拥有全部权限及用户管理；招聘人员操作招聘业务；只读用户仅查看。当前为全局角色权限，未按岗位所有者做数据隔离。

已有 SQL 表结构确认后，首次部署在 backend 目录执行：

```powershell
uv sync
uv run python -m scripts.create_admin
```

按提示在本机输入用户名、显示姓名和非空密码（最多 128 位）（密码输入不回显）。该命令只允许初始化首位有效管理员，不打印哈希或密码、不创建/覆盖默认账号。已有管理员应在前端“用户管理”创建其他账号。然后重启后端、刷新前端进入登录页。新建或重置密码的用户先修改初始密码，之后才能操作业务。SQL 已执行过无需再导入或重复设置授权。

配置：AUTH_COOKIE_SECURE=false 仅用于本地 HTTP；Ubuntu 生产 HTTPS 设置为 true。AUTH_SESSION_HOURS=8，AUTH_IDLE_MINUTES=30。AUTH_DOCS_ENABLED=false 默认关闭 /docs、/redoc、/openapi.json；仅本地开发按需开启。前后端通过同源 /api 代理，跨来源开发时精确配置 CORS_ORIGINS，禁止使用任意通配来源。

实现使用 Argon2id 密码哈希、数据库随机会话摘要和 HttpOnly Cookie；写请求验证 CSRF 与来源。数据库不保存原始会话令牌，前端不把密码或登录令牌写入 localStorage。退出、改密、停用或管理员吊销会话后立即失效；修改用户资料/角色也要求该用户重新登录。最后一个启用管理员不能被降级或停用。登录连续失败 5 次临时锁定 15 分钟，另按连接来源限制请求频率。生产反向代理须正确限制可被信任的代理来源。

审核、发布和外部动作授权的 operator_name 由服务端替换为当前登录身份；审计 Event.details 写入 actor_user_id、actor_username 和当时姓名，历史记录不回填。会话管理不依赖招聘工作流运行锁，失锁时仍可退出或修改密码，招聘写操作继续被拦截。

会话定期清理可按部署环境设置每日 cron 调用 `uv run python -m scripts.cleanup_auth_sessions`，仅删除过期或吊销超过七天的 auth_sessions；未在本次开发中执行该清理命令。权限表不自动建表/补授权，执行入口仍为 sql/08-auth-rbac.sql。


当前硬条件口径（2026-11-16）：只有可定位且能够确认满足的原文依据才判为满足；未找到依据、引用与结论不一致、引用无效或仍无法确认，统一判为不满足，理由说明“未找到能够确认满足的有效原文依据”。这表示本轮简历筛选未达到要求，不声称候选人实际没有能力。仍按 all/any 组合，任一必需条件不满足即不推荐并跳过评分；年限明确满足的条款不受其他条款影响。旧结果与节点缓存不自动改写，重启后端并创建新的评估记录后使用新口径。


当前新建评估采用 `hard_conditions_verified_v2`：硬条件筛选后执行 `verify_hard_conditions` 复核，明确不合格结束；其余候选人提取评分证据并执行 `verify_scoring_evidence`，最后由代码计算分数。证据必须定位原文，硬条件信息不足进入人工审核。单段正文通常需要 2 次（硬条件淘汰）或 4 次语义调用；分段和重试会增加调用次数，不应以固定两次估算成本。

重启后端后新建评估生效，旧记录按快照保持兼容，无需 SQL 迁移。硬条件筛选覆盖完整正文；超过 LLM_DOCUMENT_CHARS 自动按段落/句子分批，单段过长时带重叠拆分，不截断后文。

题目演示可显式设置 `EXTERNAL_SERVICES_MOCK=true` 并重启。会议与通知仍需批准当前预览版本；动作 provider 为 `mock`，响应含 `simulated=true`，不发生真实发送。默认关闭模拟模式，真实平台未配置时仍返回未配置状态。`EXTERNAL_ACTION_TIMEOUT=30` 限制单次创建、发送及查询；超时保持 uncertain，必须核实后再决定重试。Mock 无持久平台账本，无法证明动作未发生时不会返回 confirmed_absent。

Python 3.12 + uv + FastAPI + MySQL 8.4 + LangGraph。MySQL 驱动已包含 RSA 认证依赖，支持 MySQL 8 默认密码认证。当前已实现岗位版本、文件与批次、三智能体流程、人工审核、批量恢复、排期候补及完整导出。会议/通知目前仅完成授权与幂等编排，具体平台适配器待用户选定后实现，不代表真实服务已接入。前端已实现岗位、统一简历评估、人工审核与面试排期。

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

前五个 Alembic revision 依次建立岗位、简历、审核、执行、排期/动作表；006 为岗位增加 deleted_at，实现删除隐藏且保留历史；SQL 固化在 revision 内，不随以后 ORM 修改而改变历史迁移。初始岗位导入可重复执行，不覆盖已有配置。数据库名必须预先存在，迁移不创建账号、不修改密码。不要在有用户数据的数据库执行 downgrade。

### 已导入 sql/01-schema.sql 的数据库

不要再无条件执行建表迁移。先运行 `uv run python -m scripts.verify_schema`，并人工核对 sql/01-schema.sql 的 CHECK、默认值及索引；只有确认完整 14 表与本仓库 revision 008 一致时，才执行 `uv run alembic stamp 008`。有结构差异或只有部分表时应先编写增量迁移对齐。检查点表仍由适配器 setup 创建，与业务表版本独立。

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
- 模型使用 OpenAI 兼容 chat/completions 协议。自部署 llama-server 配置 `LLM_PROVIDER=llama`、`LLAMA_BASE_URL=http://127.0.0.1:8080/v1`、`LLM_MODEL_NAME=服务中的模型名`，启用鉴权时填写 `LLAMA_API_KEY`，未启用时可留空。`LLAMA_MAX_TOKENS` 控制本地输出预算，建议 8192；`LLM_TIMEOUT` 建议 300 秒。本地思考开关通过 `chat_template_kwargs.enable_thinking` 传递。
- 切回百炼使用 `LLM_PROVIDER=dashscope` 及原 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`；云端凭证不会转发给本地模型。BASE_URL 均填写 API 根路径，不含 /chat/completions。修改配置后重启后端。
- Docker 容器中的 `127.0.0.1` 指容器自身；llama-server 在宿主机时需填写容器可访问的宿主机地址，并确认服务监听及网络可达。
- 模型未配置或调用失败时记录候选人失败，不回退固定分数；模型超时/限流最多重试两次。
- 原件、本地解析正文 和历史逐页文本位于 backend/storage，运行产物被 Git 忽略。默认并发为 3，每份 PDF 上限 20MB，每批最多 250 份；生产批次使用真实上传，不填充演示数据。

## 4. 业务操作顺序

1. 新建岗位草稿，编辑规则，发布；或使用初始化岗位 v1。发布需要当前 draft_version，每次发布会推进草稿版本。
2. 在简历评估页面选择岗位并上传 PDF，选择已发布规则后执行“导入并评估”，自动提取全文并评分。原件按哈希去重，执行时复制不可变规则快照。
3. 启动批次，轮询进度与事件。顺序执行 parse_pdf → analyze_resume → evaluate_candidate → review_evaluation → summarize_result。
4. 推荐或需要复核者等待人工操作。通过 review_version 提交补充、批准或暂缓；补充需 description/source，不自动批准。批准后按原 thread_id 恢复，不重复成功节点。
5. 评估稳定后配置互不重叠的实际 45 分钟时段，为有效批准者统一排序排期。时间必须携带时区偏移；满额/冲突候补，后批准者不挤出已有预约。
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

## 岗位管理更新

岗位 API 支持名称搜索、状态筛选、重新启用和 DELETE 删除。删除使用 deleted_at 从管理列表隐藏，既有发布版本、批次与评估均保留；被删除岗位不允许新增批次、编辑或再次发布。

已有 Alembic 005 的数据库执行 `uv run alembic upgrade head`；使用旧 SQL 直接建表且尚未接管迁移的库，可核对列后执行一次 sql/03-job-soft-delete.sql。新版 01-schema.sql 已含该列，不要重复执行 03。当前配置的服务器已增量加入该列，原有 1 个岗位仍保留并正常出现在默认列表中。


## 岗位简历工作区与独立导入

新增 `/resumes` 页面按岗位管理简历。单文件和多文件使用同一个上传接口；后端计算 SHA-256，与浏览器在 HTTPS/localhost 下提交的哈希（如有）比对。同一岗位相同内容只保留一个可见关联，跨岗位复用文件和解析结果。详情与从工作区创建评估批次前重新核验原件哈希；原件损坏可用同内容文件重新上传恢复。

导入图顺序为 prepare_import → parse_pdf → save_import_result：校验原件 SHA-256、本地 PyMuPDF 提取并保存整份正文、确认产物完成。任务与节点状态写入 MySQL，IMPORT_CONCURRENCY 控制后台任务数量。当前前端一次提交导入并评估，解析成功后继续评分。

新导入仅支持 PDF，已移除 Word 转换分支和 LibreOffice 依赖；原 DOCX 历史记录仍保留，不再接收新 Word 文件。新结果写入 parsed/{file_id}/imports/{task_id}/document.md、normalized.md、sources.json，不写 file_pages 或 page_count。标准化仅去除首尾空白，不改写事实或按页拆分；sources.json 保存 file_id、block_id=document、正文路径及文本哈希。

短简历整份输入简历分析智能体；超长内容在 LLM_DOCUMENT_CHARS（默认 30000 字符）预算内按 Markdown 标题或完整段落打包，单段超过预算明确报错，不静默截断。新证据使用 file_id/block_id/quote，page_no 为 null；服务端验证引用确实出现在该正文中。历史页码证据继续兼容，前端新证据打开解析正文，旧证据仍可查看原 PDF。

失败和中断任务重试时直接从本地原件提取正文，旧远端任务标识不再使用。

前端“重新解析”仅在本地更新正文，保留历史评分。已解析历史缓存仍可读取；需要切换为新的本地结果时显式重新解析。

数据库 head 为 008：007 对应 sql/04-resume-import.sql，008 对应 sql/05-job-resumes.sql。新库使用新版 01-schema.sql（14 表）或 Alembic 初始化；旧 SQL 库只执行尚未应用的 04、05。不要对已手工升级的库重复运行相同 Alembic 迁移；先 verify_schema 并核对约束和默认值后接管。

当前配置库已存在 04 的结构，本轮仅补建 job_resumes 并回填历史关联。已有 jobs/files/batches/candidates 各 1 条保持不变，未修改历史评分、原件或规则，也未启动真实简历评估。数据库未执行 stamp。


## 简历统一评估（移除独立批次管理）

前端统一从 /resumes 管理简历、确认规则并开始评估，移除独立批次列表/详情页面及手动命名/创建步骤。POST /api/jobs/{job_id}/evaluate 负责一次提交并排队，同 request_id 持久化去重；列表返回 latest_evaluation，详情保留历史评估、人工审核、日志及单人导出。旧上传创建批次接口已移除。

底层 batches 表及已有记录保留，作为规则快照、执行恢复和排期关联，不面向用户管理；本轮无数据库结构修改、无真实模型调用。面试排期仍按原执行记录稳定排序，避免改动已有预约。


## 启动时工作流运行锁被占用

同一数据库只允许一个后端执行实例，包括不同端口、本机与 Ubuntu/Docker 部署。数据库命名锁保护任务恢复，不能简单禁用该检查。FastAPI 堆栈中 merged_lifespan 是路由生命周期组合，实际错误看末尾的工作流锁提示。

启动默认等待旧实例 65 秒（STARTUP_LOCK_WAIT_SECONDS，可配置 0–120），便于开发重载交接。退出时先 RELEASE_LOCK，再销毁专用物理连接，避免异常后带锁回到连接池。若仍冲突，新错误会给出持锁连接 ID；先停止旧 PyCharm/Uvicorn/Docker 实例，不能仅换端口或加 workers。

可在 Navicat 只读查询：

```sql
SELECT IS_USED_LOCK('hireagent:hireagent') AS owner_connection_id;
```

锁随所属数据库连接释放，事务回滚不会释放命名锁；其他连接执行 RELEASE_LOCK 不能代替持有者解锁。无法确认持有者时不要自动终止连接，应先核实旧后端，必要时由有权限的管理员在确认后关闭对应连接。不要重启整个 MySQL 或删除表来处理运行锁。


## 本地 PDF 全文提取

使用 app/clients/pdf_client.py 的 PDFClient，通过 PyMuPDF 在后台线程读取 PDF，并以空行合并各页正文。不上传解析服务、不保存页码、不写新的 file_pages 记录。证据按 file_id/block_id=document/quote 引用全文。加密、损坏、没有可读文字的文件返回明确错误；纯扫描件需要先完成 OCR。

验证：uv run pytest -q test/unit/test_pdf_client.py test/integration/test_local_pdf_import.py。测试使用生成的 PDF，运行实际本地解析器。

## 运行锁心跳与异常退出回收

专用运行锁连接设置 SESSION wait_timeout=60，每 10 秒验证 IS_USED_LOCK(name)=CONNECTION_ID()，单次心跳最多 5 秒。只修改该专用连接的会话配置，不修改 MySQL 全局参数或普通业务连接。正常实例持续保活；异常退出且服务器未立即发现断连时，空闲会话在约 60 秒后由 MySQL 关闭并释放命名锁。

默认配置（已补充到本地 .env 和 .env.example；保留用户自定义值）：

```dotenv
STARTUP_LOCK_WAIT_SECONDS=65
RUNTIME_LOCK_IDLE_TIMEOUT=60
RUNTIME_LOCK_HEARTBEAT_INTERVAL=10
RUNTIME_LOCK_HEARTBEAT_TIMEOUT=5
```

心跳间隔加请求超时必须小于空闲超时。启动等待覆盖默认会话超时，便于一次启动等待旧连接回收；若确有其他正常实例运行，仍会拒绝第二实例，不自动 KILL 其他连接，也不自动重新抢锁。

心跳失败、超时或发现持有者变化后：标记本实例失锁，取消本地评估/导入任务，阻止新任务入队；所有写请求返回 503，GET /api/health/ready 返回 503，读取与存活检查仍可用。释放/关闭专用连接前先停止心跳，避免同一连接并发执行。需要重启后端重新获取锁；已经送到外部平台的请求无法由取消本地等待撤回。

旧版本已建立的残留连接没有这个会话超时设置，部署新代码不会追溯修改它；首次升级若仍被旧连接占用，需要先确认并停止旧实例或由管理员授权清理一次。之后新版本锁连接按上述规则自动回收。该机制不能替代本地/服务器分库及单 worker 约束。

验证：隔离测试覆盖心跳所有权、超时、断连、任务取消、写请求/就绪检查隔离及重复关闭；另用随机命名的真实 MySQL 测试锁验证了持续心跳保活、停止心跳后空闲自动释放和失锁检测。未操作业务运行锁、未启动真实简历工作流。

## 统一解析评估与按 Agent 组织（2026-11-15）

当前前端使用一次“导入并评估”：绑定已发布岗位规则，后台连续完成 本地全文解析、事实提取、评分和阈值分流。达到推荐阈值且硬条件与证据完整者自动进入面试队列；临界分数或信息不足者才调用复核 Agent，再等待人工确认；明确不达标者结束。没有可用面试时段时进入候补。自动准入在 Review/Event 中明确记录“系统自动分流”，不冒充人工决定。

Agent 代码按职责拆分：resume_evaluation_agent 统一负责 PDF 导入、分析、评分、分流与二次复核；interview_agent 保存面试准入与统一排期。recruitment_agent 仅保留总图、共享 State 和历史导入兼容。技术运行时继续负责检查点、并发、持久化、恢复和人工中断。

导入任务与评估任务共享解析缓存及持久化进度，不重复执行同一活动解析。评分请求保留 request_id 幂等；相同内容重复导入不会自动创建另一份已有评估。完成后统一排序排期，不让并发候选人抢时段；重启恢复会补做已完成评估的排期。会议与通知继续使用原有预览和人工授权接口。

无需 SQL 迁移。旧审批记录、页证据和中断工作流保留；旧代码导入路径只作兼容，新实现位于各 Agent 目录。具体模型/会议服务的真实端到端验收不由隔离测试代替。


旧 .env 中的 MINERU_* 不再读取，可自行移除；配置示例和运行时已移除对应设置。不需要数据库迁移。旧解析缓存和历史页证据保留兼容；新解析 page_count=null、page_no=null，来源索引不含页码。既有下载失败记录在简历列表点击“重试评估”，将本地提取正文后继续评分。

## 评估管理查询

GET /api/evaluations 聚合已结束评估结果，按岗位规则快照分为高分、临界、低分和无总分；支持岗位、关键词、分数闭区间、人工处理/排期状态、历史开关和分页。默认按岗位/文件保留最近一次已结束结果，避免同一简历重评重复计数。服务位于 services/review_service/evaluations.py，接口位于 api/review_api/evaluation_router.py。前端复用原审核、时段与排期接口，不增加表或修改数据库。

## Agent 目录合并与节点拆分（当前实现）

import_agent 已并入 resume_evaluation_agent，导入图和 ImportState 位于该目录。所有节点实现移到各自 Agent 的 nodes/<节点名>.py，不再集中在 agent.py 或 Runtime 的节点名称分支中；各运行时只负责通用调度、事务、进度、审计和恢复。招聘图节点名称与输入输出未改变，保留既有 MySQL 检查点和历史日志兼容。完整目录与职责见 backend/app/agents/README.md。

当前最终保留三个 Agent：recruitment_agent 负责总编排与人工中断；resume_evaluation_agent 合并原导入/复核职责，负责解析、分析、评分、分流与二次复核；interview_agent 负责面试准入与排期。每个节点继续独立保存于所属 Agent 的 nodes/ 下，原检查点节点名称及日志记录保持兼容。详见 backend/app/agents/README.md。

## 高分自动排期与无效数据清理

评估管理新增“高分自动排期”：未勾选记录时处理当前岗位（或全部在招岗位）的符合条件高分结果，勾选后只检查这些记录。使用已配置的未来可用时段；证据不足、待复核、技术失败及已删除记录不会自动准入；无时段进入候补。添加或修改可用时段后自动安排已准入候补，预约幂等；会议/通知仍须独立预览与授权。

列表支持单条删除和勾选批量删除无效评估，提交前明确确认。已准入面试、已有预约或运行中的记录受到保护。删除从业务列表隐藏，原件、解析历史、检查点及审计日志保留；审核和重试不能恢复已删除记录。当前页勾选期间暂停背景轮询，避免用户选择被刷新清除；操作后重读列表。后端使用现有 events 保存删除标记，不需要 SQL 迁移。未通过开发工具清理任何真实记录。

## 按起始时间生成自动排期（当前默认）

评估管理点击“高分自动排期”，填写北京时间起始时间和可选面试官。从指定起点连续生成每人 45 分钟的时段，按高分及规则优先级分配，已有预约不移动，面试官冲突自动顺延。取消原四时段限制；超过四位候选人也可生成。重复提交保留既有预约，不重复占位。新增时段/预约有独立审计事件，会议与通知仍需授权。

前端必填起始时间，接口保留未传 starts_at 时使用已配置时段的兼容模式。时间按 UTC 保存、Asia/Shanghai 展示；无 SQL 迁移。生成是连续安排，每人 45 分钟。

## 检查点二进制兼容与审核恢复

当前 aiomysql 0.3.2 会调用 PyMySQL 1.2.4 中已经不再是函数的 escape_bytes_prefixed，导致保存 LangGraph 二进制检查点时出现 TypeError。mysql_compat.py 仅在该别名不可调用时安装十六进制二进制字面量适配；保留正常驱动函数，不修改第三方安装文件。MySQLClient 在创建连接前安装适配，启动健康检查增加只读二进制参数往返，尽早发现同类问题。依赖暂限定 PyMySQL <1.3，升级驱动时重新验证。上游代码参考：[aiomysql connection](https://github.com/aio-libs/aiomysql/blob/main/aiomysql/connection.py)、[PyMySQL converters](https://github.com/PyMySQL/PyMySQL/blob/main/pymysql/converters.py)。

执行 `uv run python -m scripts.verify_checkpoint_recovery` 可验证真实 MySQL 的中断持久化、全部 256 种字节往返、新连接恢复和测试线程删除。该脚本只使用现有检查点表和随机 UUID 测试线程，不执行 DDL、不启动业务运行时、不读取简历或请求模型。

重启后端后，评估管理对审核交接失败的记录提供“恢复待审核”。`POST /api/candidates/{id}/restore-review` 只接受未删除、失败于 human_review、尚待审核且需要复核的记录，并要求解析、分析、评分、分流、复核和汇总均有完整成功缓存；否则返回 409。恢复复用缓存，不请求模型、不代替人工决定，操作记入 review_recovery_requested 事件。其他失败继续使用原重试入口。旧记录不会在本次修复中自动重跑，无需 SQL 迁移。

模型结构错误在现有三次请求预算内重试，反馈仅包含字段路径和错误类型；支持完整 JSON 代码围栏，仍保留结构及证据校验。输出被截断时明确提示调整 LLM_MAX_TOKENS 或缩短正文。运行异常日志保存候选人 ID 与异常类型，不记录模型正文、SQL 参数或密钥。
