"""文件批次与候选人."""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None
TABLES = ["files", "file_pages", "batches", "candidates"]


def upgrade():
    op.execute(
        "CREATE TABLE files (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,\n    original_name VARCHAR(255) NOT NULL,\n    storage_path VARCHAR(1024) NOT NULL COMMENT '相对 backend/storage 的受管路径',\n    size_bytes BIGINT UNSIGNED NOT NULL,\n    media_type VARCHAR(100) NOT NULL DEFAULT 'application/pdf',\n    parse_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/completed/failed',\n    page_count INT UNSIGNED NULL,\n    parse_error TEXT NULL,\n    parsed_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_files_sha256 (sha256),\n    CONSTRAINT ck_files_parse CHECK (parse_status IN ('pending', 'running', 'completed', 'failed'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )
    op.execute(
        "CREATE TABLE file_pages (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    file_id BIGINT UNSIGNED NOT NULL,\n    page_no INT UNSIGNED NOT NULL,\n    text_path VARCHAR(1024) NOT NULL COMMENT '逐页 UTF-8 文本路径，相对 backend/storage',\n    text_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,\n    char_count INT UNSIGNED NOT NULL DEFAULT 0,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_file_page (file_id, page_no),\n    CONSTRAINT fk_page_file FOREIGN KEY (file_id) REFERENCES files (id),\n    CONSTRAINT ck_page_number CHECK (page_no > 0)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )
    op.execute(
        "CREATE TABLE batches (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    name VARCHAR(200) NOT NULL,\n    job_id BIGINT UNSIGNED NOT NULL,\n    rule_version_id BIGINT UNSIGNED NOT NULL,\n    rule_snapshot JSON NOT NULL COMMENT '创建批次时复制发布快照，禁止静默改规则',\n    status VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/evaluation_done',\n    started_at DATETIME(6) NULL,\n    evaluation_completed_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    KEY idx_batches_created (created_at),\n    KEY idx_batches_status (status),\n    CONSTRAINT fk_batch_rule FOREIGN KEY (job_id, rule_version_id) REFERENCES job_rule_versions (job_id, id),\n    CONSTRAINT ck_batch_status CHECK (status IN ('pending', 'running', 'evaluation_done'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )
    op.execute(
        "CREATE TABLE candidates (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    batch_id BIGINT UNSIGNED NOT NULL,\n    file_id BIGINT UNSIGNED NOT NULL,\n    original_filename VARCHAR(255) NOT NULL COMMENT '本次上传文件名，允许跨批次同文件异名',\n    workflow_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '应用生成 UUID，LangGraph thread_id',\n    name VARCHAR(200) NULL,\n    contact_info JSON NULL COMMENT '仅展示与通知，人工确认后使用，不进入评分',\n    processing_status VARCHAR(24) NOT NULL DEFAULT 'pending',\n    current_node VARCHAR(64) NULL,\n    checkpoint_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '仅供定位，不替代检查点',\n    extracted_facts JSON NULL,\n    evidence JSON NULL COMMENT 'evidence_id/file_id/page_no/quote/fact_ids/dimension_ids',\n    hard_conditions JSON NULL,\n    dimension_scores JSON NULL,\n    total_score DECIMAL(5,2) NULL COMMENT '服务端求和；未评估或分数无效为 NULL，不填 0',\n    recommendation VARCHAR(24) NULL COMMENT 'recommended/needs_review/deferred；技术失败可为空',\n    missing_fields JSON NULL,\n    risks JSON NULL,\n    review_notes JSON NULL COMMENT '复核智能体意见',\n    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,\n    model_id VARCHAR(200) NULL,\n    prompt_versions JSON NULL,\n    review_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/deferred',\n    review_version INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '人工操作乐观锁，成功操作递增',\n    schedule_status VARCHAR(16) NOT NULL DEFAULT 'unscheduled' COMMENT 'unscheduled/scheduled/waitlisted',\n    waitlist_reason TEXT NULL,\n    retry_count INT UNSIGNED NOT NULL DEFAULT 0,\n    error_node VARCHAR(64) NULL,\n    error_message TEXT NULL,\n    started_at DATETIME(6) NULL,\n    completed_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_candidate_batch_file (batch_id, file_id),\n    UNIQUE KEY uk_candidate_workflow (workflow_id),\n    UNIQUE KEY uk_candidate_batch_id (batch_id, id),\n    KEY idx_candidate_batch_status (batch_id, processing_status),\n    KEY idx_candidate_batch_review (batch_id, review_status),\n    KEY idx_candidate_batch_score (batch_id, total_score),\n    CONSTRAINT fk_candidate_batch FOREIGN KEY (batch_id) REFERENCES batches (id),\n    CONSTRAINT fk_candidate_file FOREIGN KEY (file_id) REFERENCES files (id),\n    CONSTRAINT ck_candidate_processing CHECK (processing_status IN ('pending', 'running', 'waiting_review', 'completed', 'failed')),\n    CONSTRAINT ck_candidate_score CHECK (total_score IS NULL OR total_score BETWEEN 0 AND 100),\n    CONSTRAINT ck_candidate_recommendation CHECK (recommendation IS NULL OR recommendation IN ('recommended', 'needs_review', 'deferred')),\n    CONSTRAINT ck_candidate_review CHECK (review_status IN ('pending', 'approved', 'deferred')),\n    CONSTRAINT ck_candidate_schedule CHECK (schedule_status IN ('unscheduled', 'scheduled', 'waitlisted'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci"
    )


def downgrade():
    op.execute("DROP TABLE candidates")
    op.execute("DROP TABLE batches")
    op.execute("DROP TABLE file_pages")
    op.execute("DROP TABLE files")
