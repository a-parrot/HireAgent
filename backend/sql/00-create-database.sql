-- 可选：仅在数据库尚不存在时，由有建库权限的账号执行。
-- Docker Compose 已创建 hireagent 时跳过本文件；不创建账号，不修改密码。
CREATE DATABASE IF NOT EXISTS hireagent
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
