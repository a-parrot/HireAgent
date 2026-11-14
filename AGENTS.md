# HireAgent 开发协作

Codex 担任主智能体：负责需求、任务拆分、接口契约、审查、集成与最终验证。

使用已注册的 `workbuddy_bridge` MCP 服务向 WorkBuddy 委派任务：

- 首先调用 `bridge_status`。`awaiting_oauth` 表示需要按 `tools/workbuddy-bridge/README.md` 完成授权；不能宣称已联通。
- 角色为 `frontend`、`backend`、`tester`。它们是任务角色，不是永久专家或已启动的独立进程。
- 当前后端为本地助理，严格串行；不得同时通过其他渠道向同一个 WorkBuddy 助理派发任务。
- 委派前明确工作目录、允许修改路径、接口约定、验收条件，并为任务提供唯一且稳定的 task_id。
- 开发任务应使用独立工作区。允许路径通过提示词传达，不构成操作系统级隔离。
- `get_result` 返回 `reported_complete` 仅表示 WorkBuddy 报告完成，必须检查改动并执行相应验证。
- `uncertain` 表示提交可能成功，不能盲目重新提交。人工在 WorkBuddy 核实任务停止后，才可调用 `resolve_task` 释放锁；该工具不会取消远端任务。
- WorkBuddy 中的权限请求由用户处理，不得自动批准。
- 当前项目未初始化 Git；不要把不存在的提交或分支当成交付物，不要在未建立版本管理的情况下并行修改。

桥接服务检查：`python tools/workbuddy-bridge/bridge.py status`

桥接服务测试：`python -m unittest discover -s tools/workbuddy-bridge -p test_bridge.py -v`
