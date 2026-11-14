# HireAgent MySQL 数据库设计

目标：MySQL 8.4、InnoDB、utf8mb4；覆盖招聘评估及独立简历导入功能。本目录提供 SQL 设计、初始化和增量升级脚本；对应 ORM 与 Alembic 位于 backend/app/models 和 backend/alembic。直接执行 SQL 与 Alembic 迁移是两种初始化入口，不要重复建表。

## 文件与执行顺序

1. `00-create-database.sql`：可选建库；Docker 已创建 hireagent 时跳过。需要建库权限，不创建账号或改密码。
2. `01-schema.sql`：创建 14 张业务表，不含 DROP、TRUNCATE 或清空数据。请先检查目标库是否已有同名业务表。
3. `02-initial-job.sql`：可选导入初始岗位和发布版本 v1；按稳定 code 去重。只导入规则，不导入候选人或固定评估结果。

在 Navicat 选择 hireagent 后打开 SQL 文件，按上述顺序执行。命令行也可在 backend/sql 目录执行（-p 后交互输入密码）：

```bash
mysql -h 127.0.0.1 -P 3306 -u hireagent_app -p hireagent < 01-schema.sql
mysql -h 127.0.0.1 -P 3306 -u hireagent_app -p hireagent < 02-initial-job.sql
```

Windows SSH 隧道连接时端口改为实际映射值，如 13306。所有文件默认 USE hireagent，自定义库名时先修改。客户端不要启用“出错继续”；DDL 不受整体事务回滚保护，若中途失败，应修复原因后核对已建表再执行。初始化 SQL 的 IF NOT EXISTS 不会把旧结构升级成新结构。

## 表与关系

| 表 | 用途 | 关键关系或约束 |
| --- | --- | --- |
| jobs | 岗位信息、草稿规则、启停、草稿编辑版本 | code 唯一；草稿可未完善 |
| job_rule_versions | 已发布岗位和规则完整快照 | 岗位内版本号唯一；应用层禁止覆盖 |
| files | 简历 SHA-256、类型、原件/产物路径和解析状态 | SHA-256 唯一，跨批次共享原件与解析产物 |
| file_import_tasks | 文件导入任务、节点进度、失败原因与时间 | task_id 唯一，file_id 关联文件 |
| job_resumes | 岗位简历关联和移除标记 | 岗位+文件唯一，历史评估保留 |
| file_pages | 页码和本地页文本索引 | 文件+页码唯一；页码从 1 开始 |
| batches | 绑定岗位版本及快照的处理批次 | 联合外键保证所选版本属于所选岗位 |
| candidates | 批次内候选人、三智能体结果、技术与业务状态 | 批次+文件唯一；workflow_id 唯一 |
| reviews | 人工操作、补充来源和流程恢复结果 | 候选人+审核版本唯一 |
| slots | UTC 起止时间、IANA 时区、面试官 | 每个时段 45 分钟；同批次起点唯一 |
| reservations | 成功预约、排序快照、外部动作预览与授权 | 候选人唯一、时段唯一；双方必须属于同批次 |
| action_records | 会议与通知执行、真实 ID、错误与待核实状态 | 预约+动作类型唯一；幂等键唯一 |
| node_executions | 节点执行状态、次数及成功输出 | 候选人+节点唯一，供恢复复用 |
| events | 批次/候选人的节点、路由、审批和错误日志 | 按批次、时间、ID 查询；候选人必须属于事件批次 |

岗位一对多发布版本；发布版本一对多批次；批次一对多候选人与时段；文件一对多页及候选人；候选人一对多审核、节点记录和事件；候选人与时段通过预约一对一配对；一个预约最多一条会议动作和一条通知动作。

表不使用级联删除，保留审批和动作追踪历史。第一版不支持预约取消重排，不以删除预约释放时段；候补保存在 candidates 的 schedule_status 与 waitlist_reason，不创建空预约。按新规则重评必须新建批次和 workflow_id。

## JSON 及状态约定

初始岗位 SQL 提供规则 JSON 格式示例：岗位信息、all/any 硬条件树、dimensions、两个阈值、sort_priority 与最终 candidate_id 排序。评分标准是初始配置，后续可编辑草稿再发布新版本；题目未给定更细的逐档评分尺度，应由招聘人员确认后配置，不声称模型评分绝对客观。

- `extracted_facts`：事实 ID、类型、描述、原文给出的起止时间、证据 ID。
- `evidence`：证据 ID、文件 ID、页码、原文片段、关联事实及维度。页文本在磁盘，证据引用真实性由应用检查。
- `hard_conditions`：条件 ID、satisfied/unsatisfied/unknown、理由和证据 ID。
- `dimension_scores`：维度 ID、分数、理由、证据 ID。总分由服务端计算，无有效评分用 NULL，不能把 NULL 当零分淘汰。
- `supplements`：人工补充事实、说明与来源，不覆盖原始模型评估。
- `action_preview`/`approved_preview`：会议参数、时间与时区、人工确认收件人、通知内容；授权快照必须绑定预览版本。
- `node_executions.output_data`：该节点的成功输出；重试只覆盖失败或未完成节点的执行状态，历史尝试写入 events，不静默重算成功节点。

所有 BIGINT ID 建议 API 返回十进制字符串，避免浏览器 Number 精度问题。时间列 DATETIME(6) 统一保存 UTC，数据库连接设置 UTC；界面与通知根据 slots.timezone 转换。外部 ID 是字符串，不套用内部整数主键。

| 维度 | 状态 |
| --- | --- |
| 批次 | pending / running / evaluation_done；evaluation_done 指所有候选人已处于待人工、最终结论或明确失败 |
| 候选人处理 | pending / running / waiting_review / completed / failed |
| 评估结论 | recommended / needs_review / deferred；技术失败允许 NULL |
| 人工审核 | pending / approved / deferred |
| 排期 | unscheduled / scheduled / waitlisted |
| 动作 | not_configured / not_executed / running / succeeded / failed / uncertain |

动作状态以 action_records 为准，候选人详情通过预约关联查询，不在多处冗余写入会议成功状态。没有动作记录时按服务配置展示未配置或未执行，不能默认成功。

## 必须由业务代码保证的规则

数据库只保存必要 CHECK、外键和唯一约束，不建设触发器或复杂规则引擎。

- 发布时校验维度总上限为 100、阈值及排序引用、禁止受保护属性；发布版本与批次快照不再修改。
- 对重复发布、编辑、审批使用短事务与行锁/版本号；审核通过需有效评估，保存决定和递增 review_version 同事务执行，补充不自动批准。
- 批次评估稳定后统一排期：总分及配置维度降序，最后候选人 ID 升序；后批准者只使用剩余时段。
- 同批次四时段及任意时间重叠由服务校验；跨批次同一面试官的重叠也需要事务内查询检查。唯一约束只能防止同一 slot_id 重复预约，不能自动发现两个不同 slot_id 的时间重叠。
- 排期锁定批次及选中时段，插入预约并更新候选人状态同事务执行；冲突回滚并读已有结果或候补。不在事务内调用模型或外部 HTTP。
- 执行动作时校验 approved_preview_version 与当前版本一致，实际使用批准快照。会议失败不通知，通知失败只重试通知；running 中进程退出或请求超时后需核实，不能直接重发。
- 原件和页文本以受管相对路径保存，应用负责路径限制、文件清理和数据库/文件一致性；日志和响应快照不存 API 密钥或无必要的完整个人资料。

## LangGraph 与 Alembic 的边界

LangGraph 检查点通过 langgraph-checkpoint-mysql 的 AIOMySQLSaver.setup 初始化，结构依赖锁定版本。本目录不创建其内部表，也不把 candidates.checkpoint_id 或 node_executions 当作完整检查点。

数据库业务写入和检查点不在同一事务。节点恢复时先读取 node_executions 的成功输出，避免业务已提交但检查点未保存导致重复执行；人工恢复结果独立记录在 reviews，后端启动时可重试失败恢复而不重复作出审批。

后续 T01–T16 任务以本设计为字段和关系基线，按阶段把对应表实现为 SQLAlchemy 模型和 Alembic 迁移，不重复设计另一套字段。SQL 直接初始化和 Alembic 是两种入口，不得初始化后再无条件执行重复建表迁移。未来只有在迁移确实覆盖同一完整结构、核对 schema 一致后才可 stamp 对应 revision；当前完整结构对应 revision 008；已有旧 SQL 库先核对并补 deleted_at、导入字段/任务表及岗位简历关联表，再进行迁移接管，不盲目 stamp head。已有部分表时应通过增量迁移对齐。

## 验证范围

本次检查脚本的表创建顺序、外键引用、索引命名、12 表覆盖、初始维度合计及重复导入语义。当前本机 Docker Engine 未运行，尚未在真实 MySQL 8.4 执行 SQL；请在目标测试库完成建表、重复初始化、初始规则导入及约束验证后再用于正式数据。

参考：[MySQL CREATE TABLE](https://dev.mysql.com/doc/refman/8.4/en/create-table.html)、[外键](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)、[CHECK](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)。

## 岗位删除字段升级

新版 01-schema.sql 包含 jobs.deleted_at。旧 SQL 库可在确认没有该列后执行一次 03-job-soft-delete.sql；已经执行迁移 006 或使用新版初始化脚本时不要重复执行。该列仅用于隐藏岗位，历史规则与批次不删除，规则自定义仍复用 JSON 字段。

## 简历独立导入升级（已实现）

- `04-resume-import.sql` / Alembic 007：files 增加文件类型、解析器信息和产物路径；新增 file_import_tasks 保存持久化导入进度。
- `05-job-resumes.sql` / Alembic 008：新增岗位简历关联 job_resumes，并从旧批次回填关联，支持按岗位查看和移除简历。
- 新库的 01-schema.sql 已包含以上结构，不再执行 04/05。旧 SQL 库只执行尚未应用的增量脚本；脚本为一次性执行，不要重复添加。Alembic 与 SQL 升级选择一个入口。
- 当前配置库已存在 04 结构，本轮补建并回填 job_resumes。原 jobs/files/batches/candidates 各 1 条保留。未修改简历原件或历史评估，未 stamp Alembic。
- 删除仅设置 job_resumes.deleted_at，原件、解析产物与候选人历史保留。重新上传相同内容可恢复岗位关联。重试新建导入任务，不覆盖旧任务记录；不引入向量表。
