"""岗位和规则版本."""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None
TABLES = ["jobs", "job_rule_versions"]


def upgrade():
    op.execute(
        "CREATE TABLE jobs (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '稳定业务编码，初始岗位导入去重',\n    name VARCHAR(200) NOT NULL,\n    responsibilities TEXT NULL,\n    requirements TEXT NULL,\n    draft_rules JSON NULL COMMENT '硬条件、维度、阈值及排序配置；草稿可未完善',\n    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active/disabled',\n    draft_version INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '编辑乐观锁版本',\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_jobs_code (code),\n    KEY idx_jobs_status_created (status, created_at),\n    CONSTRAINT ck_jobs_status CHECK (status IN ('active', 'disabled'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )
    op.execute(
        "CREATE TABLE job_rule_versions (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    job_id BIGINT UNSIGNED NOT NULL,\n    version_no INT UNSIGNED NOT NULL,\n    rule_snapshot JSON NOT NULL COMMENT '岗位信息与规则完整快照，发布后应用层禁止更新',\n    published_by VARCHAR(128) NULL COMMENT '操作人标识，不依赖账号系统',\n    published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_rule_job_version (job_id, version_no),\n    UNIQUE KEY uk_rule_job_id (job_id, id),\n    CONSTRAINT fk_rule_job FOREIGN KEY (job_id) REFERENCES jobs (id),\n    CONSTRAINT ck_rule_version CHECK (version_no > 0)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )


def downgrade():
    op.execute("DROP TABLE job_rule_versions")
    op.execute("DROP TABLE jobs")
