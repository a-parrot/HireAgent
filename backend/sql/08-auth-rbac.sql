-- HireAgent MySQL 8.4：登录与角色权限新增表。
-- 手动执行：先选择正确数据库；自定义库名请修改 USE。
-- 仅创建独立权限表，不修改或清空招聘业务表，不创建 MySQL 数据库账号。
-- IF NOT EXISTS 不会修复已有同名表的结构差异。
-- 不预置应用用户或默认密码，后续通过应用初始化脚本创建首位管理员。
USE hireagent;
SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS auth_roles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_auth_roles_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='应用角色；每个用户一个角色';

CREATE TABLE IF NOT EXISTS auth_permissions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_auth_permissions_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='后端接口功能权限';

CREATE TABLE IF NOT EXISTS auth_role_permissions (
    role_id BIGINT UNSIGNED NOT NULL,
    permission_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (role_id, permission_id),
    KEY idx_auth_role_permissions_permission (permission_id),
    CONSTRAINT fk_auth_role_permissions_role FOREIGN KEY (role_id) REFERENCES auth_roles (id),
    CONSTRAINT fk_auth_role_permissions_permission FOREIGN KEY (permission_id) REFERENCES auth_permissions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色与权限关联';

CREATE TABLE IF NOT EXISTS auth_users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL COMMENT '登录名；应用统一去除首尾空格，大小写不敏感',
    display_name VARCHAR(128) NOT NULL COMMENT '业务审核与操作人显示名称',
    password_hash VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '应用生成的 Argon2id 编码哈希，包含盐与参数；禁止明文或普通 SHA256 密码',
    role_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active/disabled；停用后所有请求立即拒绝',
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE COMMENT '管理员创建或重置密码后须修改密码',
    failed_login_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    locked_until DATETIME(6) NULL COMMENT '登录失败临时锁定截止时间，UTC',
    password_changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_login_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_auth_users_username (username),
    KEY idx_auth_users_role (role_id),
    KEY idx_auth_users_status (status),
    CONSTRAINT fk_auth_users_role FOREIGN KEY (role_id) REFERENCES auth_roles (id),
    CONSTRAINT ck_auth_users_status CHECK (status IN ('active', 'disabled')),
    CONSTRAINT ck_auth_users_must_change CHECK (must_change_password IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='应用登录用户，与 MySQL root 或数据库账号无关';

CREATE TABLE IF NOT EXISTS auth_sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '高熵随机登录令牌的 SHA256 十六进制摘要，不存原令牌',
    csrf_token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '该会话 CSRF 随机令牌摘要，用于 Cookie 会话的写请求校验',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NOT NULL COMMENT '绝对过期时间；应用另按 last_seen_at 检查空闲超时',
    revoked_at DATETIME(6) NULL COMMENT '退出、改密或管理员吊销后立即失效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_auth_sessions_token_hash (token_hash),
    KEY idx_auth_sessions_user_revoked (user_id, revoked_at),
    KEY idx_auth_sessions_expires (expires_at),
    CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id) REFERENCES auth_users (id),
    CONSTRAINT ck_auth_sessions_expiry CHECK (expires_at > created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='可撤销的服务端登录会话';

-- 初始化角色与权限；只补缺失记录，不覆盖已有名称。
-- 下列授权是初始化规则：重复执行会补回这些默认授权，不用于日常权限变更。
START TRANSACTION;

INSERT INTO auth_roles (code, name, description)
SELECT 'admin', '管理员', '系统用户与全部招聘业务管理'
WHERE NOT EXISTS (SELECT 1 FROM auth_roles WHERE code = 'admin');
INSERT INTO auth_roles (code, name, description)
SELECT 'recruiter', '招聘人员', '岗位配置、简历处理、评估审核与面试安排'
WHERE NOT EXISTS (SELECT 1 FROM auth_roles WHERE code = 'recruiter');
INSERT INTO auth_roles (code, name, description)
SELECT 'viewer', '只读用户', '查看岗位、简历、评估、面试和历史，不得修改或审核'
WHERE NOT EXISTS (SELECT 1 FROM auth_roles WHERE code = 'viewer');

INSERT INTO auth_permissions (code, name, description)
SELECT seed.code, seed.name, seed.description FROM (
    SELECT 'jobs.read' AS code, '查看岗位' AS name, '岗位及规则版本查询' AS description
    UNION ALL SELECT 'jobs.write', '管理岗位', '新增、编辑、发布、停用、删除岗位及评分规则'
    UNION ALL SELECT 'resumes.read', '查看简历', '简历详情、正文、原件预览与下载'
    UNION ALL SELECT 'resumes.write', '管理简历', '上传、重解析、移除岗位下简历'
    UNION ALL SELECT 'evaluations.read', '查看评估', '查询评估、评分证据与结果导出'
    UNION ALL SELECT 'evaluations.run', '执行评估', '新建、启动、重试评估与恢复待审核'
    UNION ALL SELECT 'evaluations.review', '人工审核', '补充说明、批准面试、暂缓'
    UNION ALL SELECT 'evaluations.delete', '清理评估', '单条或批量软删除无效评估'
    UNION ALL SELECT 'schedules.read', '查看排期', '查询时段、预约与面试安排'
    UNION ALL SELECT 'schedules.write', '管理排期', '时段编辑、自动排期、改期及取消预约'
    UNION ALL SELECT 'actions.execute', '执行外部动作', '会议和通知预览、授权、重试与结果核实，仍须业务明确授权'
    UNION ALL SELECT 'history.read', '查看历史', '历史解析、节点执行、审核及操作日志'
    UNION ALL SELECT 'users.manage', '管理用户', '用户创建、角色分配、停启用、密码重置及会话吊销'
) AS seed
WHERE NOT EXISTS (SELECT 1 FROM auth_permissions p WHERE p.code = seed.code);

-- 管理员：全部已定义权限。
INSERT INTO auth_role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM auth_roles r CROSS JOIN auth_permissions p
WHERE r.code = 'admin'
  AND NOT EXISTS (SELECT 1 FROM auth_role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- 招聘人员：显式列举业务权限，不自动获得将来新增的权限。
INSERT INTO auth_role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM auth_roles r CROSS JOIN auth_permissions p
WHERE r.code = 'recruiter'
  AND p.code IN ('jobs.read', 'jobs.write', 'resumes.read', 'resumes.write',
    'evaluations.read', 'evaluations.run', 'evaluations.review', 'evaluations.delete',
    'schedules.read', 'schedules.write', 'actions.execute', 'history.read')
  AND NOT EXISTS (SELECT 1 FROM auth_role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- 只读用户：包含简历原件读取；无任何业务写权限。
INSERT INTO auth_role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM auth_roles r CROSS JOIN auth_permissions p
WHERE r.code = 'viewer'
  AND p.code IN ('jobs.read', 'resumes.read', 'evaluations.read', 'schedules.read', 'history.read')
  AND NOT EXISTS (SELECT 1 FROM auth_role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

COMMIT;

-- 执行结果应为：admin 13，recruiter 12，viewer 5；不包含任何用户账号。
SELECT r.code AS role_code, r.name AS role_name, COUNT(rp.permission_id) AS permission_count
FROM auth_roles r LEFT JOIN auth_role_permissions rp ON rp.role_id = r.id
GROUP BY r.id, r.code, r.name ORDER BY r.id;
