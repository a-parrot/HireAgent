-- 已使用旧版 01-schema.sql 初始化的数据库，先确认 jobs 没有 deleted_at，再执行一次。
-- 不清空、不删除岗位；已有岗位该列为 NULL，继续正常显示。
USE hireagent;
ALTER TABLE jobs ADD COLUMN deleted_at DATETIME(6) NULL COMMENT '软删除时间，保留历史版本和批次';
