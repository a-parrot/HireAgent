"""节点执行与日志."""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None
TABLES = ["node_executions", "events"]


def upgrade():
    op.execute(
        "CREATE TABLE node_executions (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    candidate_id BIGINT UNSIGNED NOT NULL,\n    node_name VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,\n    status VARCHAR(16) NOT NULL DEFAULT 'pending',\n    output_data JSON NULL COMMENT '成功节点输出，用于恢复复用；不存完整 PDF',\n    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,\n    error_message TEXT NULL,\n    started_at DATETIME(6) NULL,\n    completed_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_node_candidate_name (candidate_id, node_name),\n    CONSTRAINT fk_node_candidate FOREIGN KEY (candidate_id) REFERENCES candidates (id),\n    CONSTRAINT ck_node_status CHECK (status IN ('pending', 'running', 'waiting', 'succeeded', 'failed'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )
    op.execute(
        "CREATE TABLE events (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    batch_id BIGINT UNSIGNED NOT NULL,\n    candidate_id BIGINT UNSIGNED NULL COMMENT '批次级事件为空',\n    node_name VARCHAR(64) NULL,\n    event_type VARCHAR(32) NOT NULL COMMENT 'started/completed/retried/reviewed/failed 等',\n    level VARCHAR(8) NOT NULL DEFAULT 'info',\n    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,\n    message TEXT NOT NULL,\n    details JSON NULL COMMENT '规则版本、路由原因等，禁止写入密钥和完整简历',\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    KEY idx_event_batch_time (batch_id, created_at, id),\n    KEY idx_event_batch_candidate (batch_id, candidate_id),\n    CONSTRAINT fk_event_batch FOREIGN KEY (batch_id) REFERENCES batches (id),\n    CONSTRAINT fk_event_candidate FOREIGN KEY (batch_id, candidate_id) REFERENCES candidates (batch_id, id),\n    CONSTRAINT ck_event_level CHECK (level IN ('info', 'warning', 'error'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )


def downgrade():
    op.execute("DROP TABLE events")
    op.execute("DROP TABLE node_executions")
