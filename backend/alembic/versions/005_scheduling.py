"""排期与外部动作."""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None
TABLES = ["slots", "reservations", "action_records"]


def upgrade():
    op.execute(
        "CREATE TABLE slots (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    batch_id BIGINT UNSIGNED NOT NULL,\n    starts_at DATETIME(6) NOT NULL COMMENT 'UTC',\n    ends_at DATETIME(6) NOT NULL COMMENT 'UTC，每次 45 分钟',\n    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai' COMMENT '展示用 IANA 时区',\n    interviewer VARCHAR(200) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_slot_batch_id (batch_id, id),\n    UNIQUE KEY uk_slot_batch_start (batch_id, starts_at),\n    KEY idx_slot_time (starts_at, ends_at),\n    CONSTRAINT fk_slot_batch FOREIGN KEY (batch_id) REFERENCES batches (id),\n    CONSTRAINT ck_slot_duration CHECK (ends_at = DATE_ADD(starts_at, INTERVAL 45 MINUTE))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )
    op.execute(
        "CREATE TABLE reservations (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    batch_id BIGINT UNSIGNED NOT NULL,\n    candidate_id BIGINT UNSIGNED NOT NULL,\n    slot_id BIGINT UNSIGNED NOT NULL,\n    priority_snapshot JSON NOT NULL COMMENT '预约时总分、排序维度及其值',\n    preview_version INT UNSIGNED NOT NULL DEFAULT 0,\n    action_preview JSON NULL COMMENT '会议参数、时区、人工确认收件人、通知内容',\n    approved_preview_version INT UNSIGNED NULL,\n    approved_preview JSON NULL COMMENT '批准时复制完整预览，不允许执行时取未批准新内容',\n    approved_by VARCHAR(128) NULL,\n    approved_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_reservation_candidate (candidate_id),\n    UNIQUE KEY uk_reservation_slot (slot_id),\n    KEY idx_reservation_batch_candidate (batch_id, candidate_id),\n    KEY idx_reservation_batch_slot (batch_id, slot_id),\n    CONSTRAINT fk_reservation_candidate FOREIGN KEY (batch_id, candidate_id) REFERENCES candidates (batch_id, id),\n    CONSTRAINT fk_reservation_slot FOREIGN KEY (batch_id, slot_id) REFERENCES slots (batch_id, id)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )
    op.execute(
        "CREATE TABLE action_records (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    reservation_id BIGINT UNSIGNED NOT NULL,\n    action_type VARCHAR(16) NOT NULL COMMENT 'meeting/notification',\n    idempotency_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,\n    status VARCHAR(24) NOT NULL DEFAULT 'not_executed',\n    provider VARCHAR(100) NULL,\n    approved_preview_version INT UNSIGNED NULL,\n    request_snapshot JSON NULL COMMENT '脱敏请求快照，不能包含 API 密钥',\n    response_data JSON NULL COMMENT '必要的脱敏服务返回',\n    external_id VARCHAR(255) NULL,\n    meeting_url TEXT NULL,\n    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,\n    last_error TEXT NULL,\n    started_at DATETIME(6) NULL,\n    completed_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_action_reservation_type (reservation_id, action_type),\n    UNIQUE KEY uk_action_idempotency (idempotency_key),\n    KEY idx_action_status (status, updated_at),\n    CONSTRAINT fk_action_reservation FOREIGN KEY (reservation_id) REFERENCES reservations (id),\n    CONSTRAINT ck_action_type CHECK (action_type IN ('meeting', 'notification')),\n    CONSTRAINT ck_action_status CHECK (status IN ('not_configured', 'not_executed', 'running', 'succeeded', 'failed', 'uncertain'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )


def downgrade():
    op.execute("DROP TABLE action_records")
    op.execute("DROP TABLE reservations")
    op.execute("DROP TABLE slots")
