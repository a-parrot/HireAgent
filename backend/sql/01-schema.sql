-- HireAgent MySQL 8.4 业务表初始化（仅新增，不清空、不覆盖已有表）。
-- 在已创建的 hireagent 库中执行；自定义库名时修改 USE。
-- IF NOT EXISTS 仅方便重复初始化，不会修正已有表结构差异。
-- 后续结构变更使用 Alembic；LangGraph 检查点表由适配器 setup 创建。
USE hireagent;
SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS jobs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '稳定业务编码，初始岗位导入去重',
    name VARCHAR(200) NOT NULL,
    responsibilities TEXT NULL,
    requirements TEXT NULL,
    draft_rules JSON NULL COMMENT '硬条件、维度、阈值及排序配置；草稿可未完善',
    status VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active/disabled',
    draft_version INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '编辑乐观锁版本',
    deleted_at DATETIME(6) NULL COMMENT '软删除时间，保留历史版本和批次',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_jobs_code (code),
    KEY idx_jobs_status_created (status, created_at),
    CONSTRAINT ck_jobs_status CHECK (status IN ('active', 'disabled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='岗位及可编辑草稿';

CREATE TABLE IF NOT EXISTS job_rule_versions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    job_id BIGINT UNSIGNED NOT NULL,
    version_no INT UNSIGNED NOT NULL,
    rule_snapshot JSON NOT NULL COMMENT '岗位信息与规则完整快照，发布后应用层禁止更新',
    published_by VARCHAR(128) NULL COMMENT '操作人标识，不依赖账号系统',
    published_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_rule_job_version (job_id, version_no),
    UNIQUE KEY uk_rule_job_id (job_id, id),
    CONSTRAINT fk_rule_job FOREIGN KEY (job_id) REFERENCES jobs (id),
    CONSTRAINT ck_rule_version CHECK (version_no > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='不可变岗位发布版本';

CREATE TABLE IF NOT EXISTS files (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    storage_path VARCHAR(1024) NOT NULL COMMENT '相对 backend/storage 的受管路径',
    size_bytes BIGINT UNSIGNED NOT NULL,
    media_type VARCHAR(100) NOT NULL DEFAULT 'application/pdf',
    file_type VARCHAR(16) NOT NULL DEFAULT 'pdf',
    parser_name VARCHAR(64) NULL,
    parser_version VARCHAR(128) NULL,
    markdown_path VARCHAR(1024) NULL,
    normalized_markdown_path VARCHAR(1024) NULL,
    source_index_path VARCHAR(1024) NULL,
    preview_pdf_path VARCHAR(1024) NULL,
    parse_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/completed/failed',
    page_count INT UNSIGNED NULL,
    parse_error TEXT NULL,
    parsed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_files_sha256 (sha256),
    CONSTRAINT ck_files_type CHECK (file_type IN ('pdf', 'docx')),
    CONSTRAINT ck_files_parse CHECK (parse_status IN ('pending', 'running', 'completed', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='简历原件索引，可被不同岗位与批次复用';

CREATE TABLE IF NOT EXISTS file_pages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    file_id BIGINT UNSIGNED NOT NULL,
    page_no INT UNSIGNED NOT NULL,
    text_path VARCHAR(1024) NOT NULL COMMENT '逐页 UTF-8 文本路径，相对 backend/storage',
    text_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    char_count INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_file_page (file_id, page_no),
    CONSTRAINT fk_page_file FOREIGN KEY (file_id) REFERENCES files (id),
    CONSTRAINT ck_page_number CHECK (page_no > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='按页原文索引，不存 PDF 二进制';

CREATE TABLE IF NOT EXISTS batches (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    job_id BIGINT UNSIGNED NOT NULL,
    rule_version_id BIGINT UNSIGNED NOT NULL,
    rule_snapshot JSON NOT NULL COMMENT '创建批次时复制发布快照，禁止静默改规则',
    status VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/evaluation_done',
    started_at DATETIME(6) NULL,
    evaluation_completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_batches_created (created_at),
    KEY idx_batches_status (status),
    CONSTRAINT fk_batch_rule FOREIGN KEY (job_id, rule_version_id) REFERENCES job_rule_versions (job_id, id),
    CONSTRAINT ck_batch_status CHECK (status IN ('pending', 'running', 'evaluation_done'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='批次；评估稳定不代表所有外部动作成功';

CREATE TABLE IF NOT EXISTS candidates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id BIGINT UNSIGNED NOT NULL,
    file_id BIGINT UNSIGNED NOT NULL,
    original_filename VARCHAR(255) NOT NULL COMMENT '本次上传文件名，允许跨批次同文件异名',
    workflow_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '应用生成 UUID，LangGraph thread_id',
    name VARCHAR(200) NULL,
    contact_info JSON NULL COMMENT '仅展示与通知，人工确认后使用，不进入评分',
    processing_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    current_node VARCHAR(64) NULL,
    checkpoint_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '仅供定位，不替代检查点',
    extracted_facts JSON NULL,
    evidence JSON NULL COMMENT 'evidence_id/file_id/page_no/quote/fact_ids/dimension_ids',
    hard_conditions JSON NULL,
    dimension_scores JSON NULL,
    total_score DECIMAL(5,2) NULL COMMENT '服务端求和；未评估或分数无效为 NULL，不填 0',
    recommendation VARCHAR(24) NULL COMMENT 'recommended/needs_review/deferred；技术失败可为空',
    missing_fields JSON NULL,
    risks JSON NULL,
    review_notes JSON NULL COMMENT '复核智能体意见',
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    model_id VARCHAR(200) NULL,
    prompt_versions JSON NULL,
    review_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/deferred',
    review_version INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '人工操作乐观锁，成功操作递增',
    schedule_status VARCHAR(16) NOT NULL DEFAULT 'unscheduled' COMMENT 'unscheduled/scheduled/waitlisted',
    waitlist_reason TEXT NULL,
    retry_count INT UNSIGNED NOT NULL DEFAULT 0,
    error_node VARCHAR(64) NULL,
    error_message TEXT NULL,
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_candidate_batch_file (batch_id, file_id),
    UNIQUE KEY uk_candidate_workflow (workflow_id),
    UNIQUE KEY uk_candidate_batch_id (batch_id, id),
    KEY idx_candidate_batch_status (batch_id, processing_status),
    KEY idx_candidate_batch_review (batch_id, review_status),
    KEY idx_candidate_batch_score (batch_id, total_score),
    CONSTRAINT fk_candidate_batch FOREIGN KEY (batch_id) REFERENCES batches (id),
    CONSTRAINT fk_candidate_file FOREIGN KEY (file_id) REFERENCES files (id),
    CONSTRAINT ck_candidate_processing CHECK (processing_status IN ('pending', 'running', 'waiting_review', 'completed', 'failed')),
    CONSTRAINT ck_candidate_score CHECK (total_score IS NULL OR total_score BETWEEN 0 AND 100),
    CONSTRAINT ck_candidate_recommendation CHECK (recommendation IS NULL OR recommendation IN ('recommended', 'needs_review', 'deferred')),
    CONSTRAINT ck_candidate_review CHECK (review_status IN ('pending', 'approved', 'deferred')),
    CONSTRAINT ck_candidate_schedule CHECK (schedule_status IN ('unscheduled', 'scheduled', 'waitlisted'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='候选人在一个批次中的评估结果';

CREATE TABLE IF NOT EXISTS reviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    candidate_id BIGINT UNSIGNED NOT NULL,
    operation VARCHAR(16) NOT NULL COMMENT 'supplement/approve/defer',
    review_version INT UNSIGNED NOT NULL COMMENT '操作成功后的版本号',
    reason TEXT NOT NULL,
    supplements JSON NULL COMMENT '补充说明与来源，不覆盖模型结果',
    operator_name VARCHAR(128) NOT NULL,
    resume_status VARCHAR(16) NOT NULL DEFAULT 'not_required' COMMENT 'not_required/pending/succeeded/failed',
    resume_error TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_review_candidate_version (candidate_id, review_version),
    CONSTRAINT fk_review_candidate FOREIGN KEY (candidate_id) REFERENCES candidates (id),
    CONSTRAINT ck_review_operation CHECK (operation IN ('supplement', 'approve', 'defer')),
    CONSTRAINT ck_review_resume CHECK (resume_status IN ('not_required', 'pending', 'succeeded', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='人工审核历史及恢复状态，追加写入';

CREATE TABLE IF NOT EXISTS slots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id BIGINT UNSIGNED NOT NULL,
    starts_at DATETIME(6) NOT NULL COMMENT 'UTC',
    ends_at DATETIME(6) NOT NULL COMMENT 'UTC，默认 45 分钟，可人工调整',
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai' COMMENT '展示用 IANA 时区',
    interviewer VARCHAR(200) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_slot_batch_id (batch_id, id),
    KEY idx_slot_time (starts_at, ends_at),
    CONSTRAINT fk_slot_batch FOREIGN KEY (batch_id) REFERENCES batches (id),
    CONSTRAINT ck_slot_duration CHECK (ends_at > starts_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='实际面试时段，批次默认配置四个';

CREATE TABLE IF NOT EXISTS reservations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id BIGINT UNSIGNED NOT NULL,
    candidate_id BIGINT UNSIGNED NOT NULL,
    slot_id BIGINT UNSIGNED NOT NULL,
    priority_snapshot JSON NOT NULL COMMENT '预约时总分、排序维度及其值',
    preview_version INT UNSIGNED NOT NULL DEFAULT 0,
    action_preview JSON NULL COMMENT '会议参数、时区、人工确认收件人、通知内容',
    approved_preview_version INT UNSIGNED NULL,
    approved_preview JSON NULL COMMENT '批准时复制完整预览，不允许执行时取未批准新内容',
    approved_by VARCHAR(128) NULL,
    approved_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_reservation_candidate (candidate_id),
    UNIQUE KEY uk_reservation_slot (slot_id),
    KEY idx_reservation_batch_candidate (batch_id, candidate_id),
    KEY idx_reservation_batch_slot (batch_id, slot_id),
    CONSTRAINT fk_reservation_candidate FOREIGN KEY (batch_id, candidate_id) REFERENCES candidates (batch_id, id),
    CONSTRAINT fk_reservation_slot FOREIGN KEY (batch_id, slot_id) REFERENCES slots (batch_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='成功预约；候补留在 candidates，不占时段';

CREATE TABLE IF NOT EXISTS action_records (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    reservation_id BIGINT UNSIGNED NOT NULL,
    action_type VARCHAR(16) NOT NULL COMMENT 'meeting/notification',
    idempotency_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'not_executed',
    provider VARCHAR(100) NULL,
    approved_preview_version INT UNSIGNED NULL,
    request_snapshot JSON NULL COMMENT '脱敏请求快照，不能包含 API 密钥',
    response_data JSON NULL COMMENT '必要的脱敏服务返回',
    external_id VARCHAR(255) NULL,
    meeting_url TEXT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    last_error TEXT NULL,
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_action_reservation_type (reservation_id, action_type),
    UNIQUE KEY uk_action_idempotency (idempotency_key),
    KEY idx_action_status (status, updated_at),
    CONSTRAINT fk_action_reservation FOREIGN KEY (reservation_id) REFERENCES reservations (id),
    CONSTRAINT ck_action_type CHECK (action_type IN ('meeting', 'notification')),
    CONSTRAINT ck_action_status CHECK (status IN ('not_configured', 'not_executed', 'running', 'succeeded', 'failed', 'uncertain'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='真实会议与通知动作；running 为重启核实提供依据';

CREATE TABLE IF NOT EXISTS node_executions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    candidate_id BIGINT UNSIGNED NOT NULL,
    node_name VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    output_data JSON NULL COMMENT '成功节点输出，用于恢复复用；不存完整 PDF',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_node_candidate_name (candidate_id, node_name),
    CONSTRAINT fk_node_candidate FOREIGN KEY (candidate_id) REFERENCES candidates (id),
    CONSTRAINT ck_node_status CHECK (status IN ('pending', 'running', 'waiting', 'succeeded', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='节点幂等执行记录，不替代 LangGraph 检查点';

CREATE TABLE IF NOT EXISTS events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    batch_id BIGINT UNSIGNED NOT NULL,
    candidate_id BIGINT UNSIGNED NULL COMMENT '批次级事件为空',
    node_name VARCHAR(64) NULL,
    event_type VARCHAR(32) NOT NULL COMMENT 'started/completed/retried/reviewed/failed 等',
    level VARCHAR(8) NOT NULL DEFAULT 'info',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    message TEXT NOT NULL,
    details JSON NULL COMMENT '规则版本、路由原因等，禁止写入密钥和完整简历',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_event_batch_time (batch_id, created_at, id),
    KEY idx_event_batch_candidate (batch_id, candidate_id),
    CONSTRAINT fk_event_batch FOREIGN KEY (batch_id) REFERENCES batches (id),
    CONSTRAINT fk_event_candidate FOREIGN KEY (batch_id, candidate_id) REFERENCES candidates (batch_id, id),
    CONSTRAINT ck_event_level CHECK (level IN ('info', 'warning', 'error'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='运行和人工事件，按时间追加';


CREATE TABLE IF NOT EXISTS file_import_tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT '应用生成的唯一任务标识，可用于 LangGraph thread_id',
    file_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        COMMENT 'pending/running/completed/failed',
    current_node VARCHAR(64) NULL
        COMMENT 'prepare_import/parse_pdf/parse_word/normalize_content/save_import_result',
    node_progress JSON NULL
        COMMENT '本次各节点状态、耗时和时间；节点执行后持久化，不保存简历正文',
    error_message TEXT NULL COMMENT '本次任务失败原因，不写密钥或简历全文',
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_import_task_id (task_id),
    KEY idx_import_file_created (file_id, created_at, id),
    KEY idx_import_status_created (status, created_at, id),
    CONSTRAINT fk_import_task_file FOREIGN KEY (file_id) REFERENCES files (id),
    CONSTRAINT ck_import_task_status
        CHECK (status IN ('pending', 'running', 'completed', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='简历导入任务与持久化节点进度；不保存岗位评估结果';

CREATE TABLE IF NOT EXISTS job_resumes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    job_id BIGINT UNSIGNED NOT NULL,
    file_id BIGINT UNSIGNED NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    deleted_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_job_resume_file (job_id, file_id),
    KEY idx_job_resume_visible (job_id, deleted_at, id),
    CONSTRAINT fk_resume_job FOREIGN KEY (job_id) REFERENCES jobs (id),
    CONSTRAINT fk_resume_file FOREIGN KEY (file_id) REFERENCES files (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='岗位简历关联；移除不删除历史评估';
