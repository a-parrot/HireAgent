# 日志与 Agent 执行追踪

后端使用 Loguru，启动后同时输出控制台和 UTF-8 文件：

- `backend/logs/hireagent.log`：请求、工作流、Agent 节点、模型调用及人工操作。
- `backend/logs/errors.log`：ERROR 及以上级别，包含错误类型、数据库错误码和调用栈位置。

默认单文件达到 20 MB 轮转，保留 14 天。目录已纳入 Git 忽略。

## 配置

在 `backend/.env` 配置，修改后重启后端：

```dotenv
LOG_LEVEL=INFO
LOG_COLORIZE=true
LOG_ROTATION=20 MB
LOG_RETENTION=14 days
# LOG_DIR=E:/vibecoding-project/HireAgent/backend/logs
```

## 查看过程

控制台按事件着色：调用中青色、完成及缓存命中绿色、待人工/重试黄色、失败红色；Agent 用不同颜色区分，时间和追踪编号弱化，节点加粗，耗时黄色。详细字段放在下一行，不重复铺满所有上下文字段。文件始终保持无 ANSI 控制码的纯文本。

默认启用颜色；不支持 ANSI 的终端可设置 `LOG_COLORIZE=false`。环境变量 `NO_COLOR` 存在时优先禁用颜色。颜色仅调整展示，不改变日志级别、记录内容或轮转规则。

```powershell
Get-Content backend/logs/hireagent.log -Tail 100 -Wait
Select-String -Path backend/logs/hireagent.log -Pattern 'candidate=227 '
Select-String -Path backend/logs/errors.log -Pattern 'failed'
```

日志字段包含 request_id、agent、candidate_id、task_id、node、span_id。节点中的模型调用继承同一候选人、任务和请求上下文；并发任务独立记录。HTTP 响应返回 `X-Request-ID`，可据此追踪请求发起的后台任务。

| 事件 | 含义 |
| --- | --- |
| `workflow.started` / `workflow.state_loaded` | 开始评估、加载工作流与批次标识 |
| `node.started` / `node.completed` | 调用节点、完成节点及耗时、判定/评分摘要 |
| `node.cache_hit` | 复用已成功节点结果，没有再次执行模型 |
| `model.request` / `model.response` | 模型名称、输出 Schema、尝试次数、输入字符量、响应耗时及服务返回的 token 用量 |
| `model.retry_http` / `model.retry_network` / `model.retry_schema` | 限流/服务错误、网络故障或结构校验失败后的有限重试 |
| `human_review.waiting_for_human` | 正常人工中断，不作为失败 |
| `review.saved` | 审核决定及恢复状态；不输出审核人姓名和理由正文 |
| `interview.*` / `external.*` | 预约、改期、取消与外部动作授权/执行 |
| `*.failed` / `*.cancelled` | 失败类型或任务取消 |

结果摘要只记录条件/评分项 ID、判定、是否命中、证据数量、总分和分流结果，不输出原文、姓名、联系方式、提示词正文、密钥、完整模型响应或思维链。异常仅记录类型、数据库数字错误码和堆栈位置，不展开变量或原始异常载荷。第三方 HTTP/SQL 日志只保留通用事件；访问日志不记录查询参数。

原数据库 `events`、`node_executions` 仍用于前端历史与审计，Loguru 文件用于实时排障，两者互补。
