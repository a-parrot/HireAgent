"""人工审批."""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None
TABLES = ["reviews"]


def upgrade():
    op.execute(
        "CREATE TABLE reviews (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    candidate_id BIGINT UNSIGNED NOT NULL,\n    operation VARCHAR(16) NOT NULL COMMENT 'supplement/approve/defer',\n    review_version INT UNSIGNED NOT NULL COMMENT '操作成功后的版本号',\n    reason TEXT NOT NULL,\n    supplements JSON NULL COMMENT '补充说明与来源，不覆盖模型结果',\n    operator_name VARCHAR(128) NOT NULL,\n    resume_status VARCHAR(16) NOT NULL DEFAULT 'not_required' COMMENT 'not_required/pending/succeeded/failed',\n    resume_error TEXT NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_review_candidate_version (candidate_id, review_version),\n    CONSTRAINT fk_review_candidate FOREIGN KEY (candidate_id) REFERENCES candidates (id),\n    CONSTRAINT ck_review_operation CHECK (operation IN ('supplement', 'approve', 'defer')),\n    CONSTRAINT ck_review_resume CHECK (resume_status IN ('not_required', 'pending', 'succeeded', 'failed'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )


def downgrade():
    op.execute("DROP TABLE reviews")
