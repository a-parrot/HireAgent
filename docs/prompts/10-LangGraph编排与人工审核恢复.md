# 10-LangGraph编排与人工审核恢复

任务编号：T10；稳定 task_id：`hireagent-t10`。

## 执行约定

你是本项目的开发 AI。工作目录为 `E:/vibecoding-project/HireAgent`；若在 Ubuntu，先定位对应的 HireAgent 项目根目录。先阅读根目录及修改路径适用的 AGENTS.md、`需求分析/招聘多智能体系统技术实现方案.md`、`docs/architecture/项目结构说明.md`、当前代码及前序验收记录。项目路径以实际工作区为准，禁止写入参考项目。

沿用 Python 3.12 + uv + FastAPI + SQLAlchemy 异步 MySQL、LangGraph 和既定目录。读取现有配置，不输出真实密码，不覆盖 .env、uv 环境或用户改动。依赖变化通过 uv 同步 pyproject.toml 与 uv.lock。只做基本格式、规则和一致性检查，不引入自动返工循环、微服务、Redis 或向量库。正常业务与演示必须使用真实数据/服务；隔离测试可用替身，但不能把替身结果当实际验收。

先核对前置条件和接口，再实施、验证、更新相关接口与启动说明。允许在任务列出的路径及本任务相关 `backend/test/`、`frontend/tests/`、`docs/api/`、README 内修改；新增迁移只能增量编写。范围外的必要修改先说明原因，无需为普通可逆实现反复请求确认。不要执行数据库清空、生产回退或未经批准的真实会议/通知。

遵循 AGENTS.md 的委派要求：如通过 WorkBuddy 执行，先 bridge_status，明确独立工作区、允许路径、接口、验收及本文件 task_id，严格串行；桥接未联通不得宣称已派发。reported_complete 后仍检查代码并验证，uncertain 时不得盲目重投。用户处理 WorkBuddy 权限请求。仅生成这些提示词不代表启动任何委派。

## 目标与前置条件

将三个智能体串联成真实候选人工作流，并实现人工中断与持久化恢复。

前置任务：T09。前序未验收时先指出缺口，完成不依赖缺口的工作，不能假设接口或数据已经存在。

## 允许修改的主要路径

- `backend/app/agents/recruitment_agent/`
- `backend/app/api/review_api/`
- `backend/app/services/review_service/`
- `backend/app/repositories/review_repo/`
- `backend/app/models/mysql/`
- `backend/alembic/`
- `backend/app/core/lifespan.py`

## 功能要求

1. 创建 recruitment_state、recruitment_graph，顺序连接解析→分析→评估→复核→汇总→人工审核或结束。
2. 使用 AIOMySQLSaver，验证与当前 LangGraph 的兼容性并初始化检查点；workflow_id 对应 thread_id，生命周期内关闭连接。
3. 新增 reviews 表及审批版本；人工节点等待补充说明、批准或暂缓，补充需注明来源且不隐式批准。
4. 审批记录和恢复具备幂等性，拒绝过期或重复决定；恢复失败保留可重试状态，不能把审批成功冒充流程恢复成功。
5. 批准后写入待排期状态；排期仍由批次统一触发；重启后不得自动批准暂停任务。

## 接口与交接

POST /api/candidates/{id}/review；详情返回当前节点、审批状态、审批版本及审核历史。本阶段先提供单候选人服务调用入口，批量启动由 T11 接入。 编码前检查前序实际字段与响应格式，补充本任务契约并保持既有调用兼容。

## 验收条件

- 真实简历运行到人工暂停，关闭后端再启动后可批准并恢复。
- 不重新解析已完成 PDF，不覆盖原模型评分。
- 重复审批不重复恢复，未经批准不进入排期。

## 交付要求

完成后报告：实现内容、修改文件、接口/迁移/配置变化、实际执行的命令与结果、未解决问题。相关后端使用 `uv run pytest` 与 `uv run ruff check app main.py test` 验证；前端按项目脚本执行类型检查和构建。数据库、模型或平台不可用时明确区分已实现与未验证，不伪造通过。将本任务记录写入 `docs/prompts/验收记录.md`，状态先为“待验收”；主智能体检查并验证后才能改为“已完成”。只完成本任务，不自动开始下一阶段。
