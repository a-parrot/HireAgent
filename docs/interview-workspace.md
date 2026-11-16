# 候选人面试排期

入口：左侧“面试排期”。按候选人展示待排期和已排期，搜索姓名、简历文件名或岗位。

- 单人：点击“安排面试”，选择开始时间，自动填入 45 分钟后的结束时间，可调整。
- 批量：勾选当前页待排期人员，点击“批量排期”。每人时长相同，支持设置场间间隔，确认前展示全部时间。按预览顺序安排，任一冲突则整批回滚。
- 改期：修改预约时间和面试官，原会议通知预览及授权失效，须重新确认。
- 取消：二次确认后回到待排期，记录保存到事件日志。
- 会议与通知：直接打开当前候选人的外部动作管理，不自动发送消息。有外部动作执行历史的预约不能直接改期或取消。

时间统一以北京时间输入、显示，接口传带偏移的 ISO 时间，数据库存 UTC。同一面试官（留空视为同一默认日历）跨批次不能重叠，不同面试官可同时面试。

## 接口

- `GET /api/interviews`：keyword、status（pending/scheduled）、page、page_size，返回候选人、岗位、预约、时段及筛选计数。
- `POST /api/interviews`：candidate_ids、starts_at、ends_at、timezone、interviewer、gap_minutes；仅准入且评分完成者可预约，重复预约返回 409。
- `PATCH /api/interviews/{reservation_id}`：起止时间、时区、面试官及 preview_version；旧版本返回 409。
- `DELETE /api/interviews/{reservation_id}?preview_version=...`：取消未执行外部动作的预约并审计。

## 数据库升级

Alembic 管理的数据库执行 `python -m alembic upgrade head`。SQL 初始化的现有数据库，先确认已应用 `06-flexible-slot-duration.sql`，再执行 `07-parallel-interviewers.sql`；也可从 backend 运行 `python -m scripts.upgrade_interview_calendar --apply`，安全检查并移除旧的起始时间唯一索引。不重复运行初始化建表脚本。
