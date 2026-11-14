# 5-批次创建与PDF上传

任务编号：T05；稳定 task_id：`hireagent-t05`。

## 执行约定

你是本项目的开发 AI。工作目录为 `E:/vibecoding-project/HireAgent`；若在 Ubuntu，先定位对应的 HireAgent 项目根目录。先阅读根目录及修改路径适用的 AGENTS.md、`需求分析/招聘多智能体系统技术实现方案.md`、`docs/architecture/项目结构说明.md`、当前代码及前序验收记录。项目路径以实际工作区为准，禁止写入参考项目。

沿用 Python 3.12 + uv + FastAPI + SQLAlchemy 异步 MySQL、LangGraph 和既定目录。读取现有配置，不输出真实密码，不覆盖 .env、uv 环境或用户改动。依赖变化通过 uv 同步 pyproject.toml 与 uv.lock。只做基本格式、规则和一致性检查，不引入自动返工循环、微服务、Redis 或向量库。正常业务与演示必须使用真实数据/服务；隔离测试可用替身，但不能把替身结果当实际验收。

先核对前置条件和接口，再实施、验证、更新相关接口与启动说明。允许在任务列出的路径及本任务相关 `backend/test/`、`frontend/tests/`、`docs/api/`、README 内修改；新增迁移只能增量编写。范围外的必要修改先说明原因，无需为普通可逆实现反复请求确认。不要执行数据库清空、生产回退或未经批准的真实会议/通知。

遵循 AGENTS.md 的委派要求：如通过 WorkBuddy 执行，先 bridge_status，明确独立工作区、允许路径、接口、验收及本文件 task_id，严格串行；桥接未联通不得宣称已派发。reported_complete 后仍检查代码并验证，uncertain 时不得盲目重投。用户处理 WorkBuddy 权限请求。仅生成这些提示词不代表启动任何委派。

## 目标与前置条件

实现绑定岗位规则版本的批次和候选人创建，保存上传原件。

前置任务：T03。前序未验收时先指出缺口，完成不依赖缺口的工作，不能假设接口或数据已经存在。

## 允许修改的主要路径

- `backend/app/api/resume_api/`
- `backend/app/schemas/`
- `backend/app/services/resume_service/`
- `backend/app/repositories/resume_repo/`
- `backend/app/models/mysql/`
- `backend/alembic/versions/`
- `backend/storage/`

## 功能要求

1. 新增 batches、candidates 及必要文件索引模型和迁移，批次绑定已发布版本及规则快照。
2. 批量上传 PDF，保存至 backend/storage/uploads，记录原始文件名、文件 ID、哈希与状态。
3. 使用生成的安全文件名，配置文件大小/数量限制；同批次同哈希幂等，不允许路径穿越。
4. 拒绝无效岗位或未发布版本，文件失败给出原因；文件与数据库写入失败时清理未引用新文件，不遗留正常候选人假记录。

## 接口与交接

POST /api/batches（multipart：岗位 ID、规则版本 ID、PDF 文件列表）；GET /api/batches/{id}、GET /api/candidates?batch_id=...、GET /api/candidates/{id} 提供当前可用字段。 编码前检查前序实际字段与响应格式，补充本任务契约并保持既有调用兼容。

## 验收条件

- 真实 PDF 批量导入成功，原件可找到，批次快照与所选版本一致。
- 重复文件不重复创建候选人，非法输入有明确错误。
- 规则新版本发布不改变既有批次快照。

## 交付要求

完成后报告：实现内容、修改文件、接口/迁移/配置变化、实际执行的命令与结果、未解决问题。相关后端使用 `uv run pytest` 与 `uv run ruff check app main.py test` 验证；前端按项目脚本执行类型检查和构建。数据库、模型或平台不可用时明确区分已实现与未验证，不伪造通过。将本任务记录写入 `docs/prompts/验收记录.md`，状态先为“待验收”；主智能体检查并验证后才能改为“已完成”。只完成本任务，不自动开始下一阶段。
