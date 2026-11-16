/*
 Navicat Premium Dump SQL

 Source Server         : test
 Source Server Type    : MySQL
 Source Server Version : 80413 (8.4.13)
 Source Host           : 152.136.30.174:3306
 Source Schema         : hireagent

 Target Server Type    : MySQL
 Target Server Version : 80413 (8.4.13)
 File Encoding         : 65001

 Date: 16/11/2026 02:13:20
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for action_records
-- ----------------------------
DROP TABLE IF EXISTS `action_records`;
CREATE TABLE `action_records`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `reservation_id` bigint UNSIGNED NOT NULL,
  `action_type` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'meeting/notification',
  `idempotency_key` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` varchar(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'not_executed',
  `provider` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `approved_preview_version` int UNSIGNED NULL DEFAULT NULL,
  `request_snapshot` json NULL COMMENT '脱敏请求快照，不能包含 API 密钥',
  `response_data` json NULL COMMENT '必要的脱敏服务返回',
  `external_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `meeting_url` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `attempt_count` int UNSIGNED NOT NULL DEFAULT 0,
  `last_error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `started_at` datetime(6) NULL DEFAULT NULL,
  `completed_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_action_reservation_type`(`reservation_id` ASC, `action_type` ASC) USING BTREE,
  UNIQUE INDEX `uk_action_idempotency`(`idempotency_key` ASC) USING BTREE,
  INDEX `idx_action_status`(`status` ASC, `updated_at` ASC) USING BTREE,
  CONSTRAINT `fk_action_reservation` FOREIGN KEY (`reservation_id`) REFERENCES `reservations` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_action_status` CHECK (`status` in (_utf8mb4'not_configured',_utf8mb4'not_executed',_utf8mb4'running',_utf8mb4'succeeded',_utf8mb4'failed',_utf8mb4'uncertain')),
  CONSTRAINT `ck_action_type` CHECK (`action_type` in (_utf8mb4'meeting',_utf8mb4'notification'))
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '真实会议与通知动作；running 为重启核实提供依据' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for batches
-- ----------------------------
DROP TABLE IF EXISTS `batches`;
CREATE TABLE `batches`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `job_id` bigint UNSIGNED NOT NULL,
  `rule_version_id` bigint UNSIGNED NOT NULL,
  `rule_snapshot` json NOT NULL COMMENT '创建批次时复制发布快照，禁止静默改规则',
  `status` varchar(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending' COMMENT 'pending/running/evaluation_done',
  `started_at` datetime(6) NULL DEFAULT NULL,
  `evaluation_completed_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_batches_created`(`created_at` ASC) USING BTREE,
  INDEX `idx_batches_status`(`status` ASC) USING BTREE,
  INDEX `fk_batch_rule`(`job_id` ASC, `rule_version_id` ASC) USING BTREE,
  CONSTRAINT `fk_batch_rule` FOREIGN KEY (`job_id`, `rule_version_id`) REFERENCES `job_rule_versions` (`job_id`, `id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_batch_status` CHECK (`status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'evaluation_done'))
) ENGINE = InnoDB AUTO_INCREMENT = 15 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '批次；评估稳定不代表所有外部动作成功' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for candidates
-- ----------------------------
DROP TABLE IF EXISTS `candidates`;
CREATE TABLE `candidates`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `batch_id` bigint UNSIGNED NOT NULL,
  `file_id` bigint UNSIGNED NOT NULL,
  `original_filename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '本次上传文件名，允许跨批次同文件异名',
  `workflow_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '应用生成 UUID，LangGraph thread_id',
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `contact_info` json NULL COMMENT '仅展示与通知，人工确认后使用，不进入评分',
  `processing_status` varchar(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending',
  `current_node` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `checkpoint_id` varchar(128) CHARACTER SET ascii COLLATE ascii_bin NULL DEFAULT NULL COMMENT '仅供定位，不替代检查点',
  `extracted_facts` json NULL,
  `evidence` json NULL COMMENT 'evidence_id/file_id/page_no/quote/fact_ids/dimension_ids',
  `hard_conditions` json NULL,
  `dimension_scores` json NULL,
  `total_score` decimal(5, 2) NULL DEFAULT NULL COMMENT '服务端求和；未评估或分数无效为 NULL，不填 0',
  `recommendation` varchar(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'recommended/needs_review/deferred；技术失败可为空',
  `missing_fields` json NULL,
  `risks` json NULL,
  `review_notes` json NULL COMMENT '复核智能体意见',
  `needs_human_review` tinyint(1) NOT NULL DEFAULT 0,
  `model_id` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `prompt_versions` json NULL,
  `review_status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/deferred',
  `review_version` int UNSIGNED NOT NULL DEFAULT 0 COMMENT '人工操作乐观锁，成功操作递增',
  `schedule_status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'unscheduled' COMMENT 'unscheduled/scheduled/waitlisted',
  `waitlist_reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `retry_count` int UNSIGNED NOT NULL DEFAULT 0,
  `error_node` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `started_at` datetime(6) NULL DEFAULT NULL,
  `completed_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_candidate_batch_file`(`batch_id` ASC, `file_id` ASC) USING BTREE,
  UNIQUE INDEX `uk_candidate_workflow`(`workflow_id` ASC) USING BTREE,
  UNIQUE INDEX `uk_candidate_batch_id`(`batch_id` ASC, `id` ASC) USING BTREE,
  INDEX `idx_candidate_batch_status`(`batch_id` ASC, `processing_status` ASC) USING BTREE,
  INDEX `idx_candidate_batch_review`(`batch_id` ASC, `review_status` ASC) USING BTREE,
  INDEX `idx_candidate_batch_score`(`batch_id` ASC, `total_score` ASC) USING BTREE,
  INDEX `fk_candidate_file`(`file_id` ASC) USING BTREE,
  CONSTRAINT `fk_candidate_batch` FOREIGN KEY (`batch_id`) REFERENCES `batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_candidate_file` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_candidate_processing` CHECK (`processing_status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'waiting_review',_utf8mb4'completed',_utf8mb4'failed')),
  CONSTRAINT `ck_candidate_recommendation` CHECK ((`recommendation` is null) or (`recommendation` in (_utf8mb4'recommended',_utf8mb4'needs_review',_utf8mb4'deferred'))),
  CONSTRAINT `ck_candidate_review` CHECK (`review_status` in (_utf8mb4'pending',_utf8mb4'approved',_utf8mb4'deferred')),
  CONSTRAINT `ck_candidate_schedule` CHECK (`schedule_status` in (_utf8mb4'unscheduled',_utf8mb4'scheduled',_utf8mb4'waitlisted')),
  CONSTRAINT `ck_candidate_score` CHECK ((`total_score` is null) or (`total_score` between 0 and 100))
) ENGINE = InnoDB AUTO_INCREMENT = 227 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '候选人在一个批次中的评估结果' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for checkpoint_blobs
-- ----------------------------
DROP TABLE IF EXISTS `checkpoint_blobs`;
CREATE TABLE `checkpoint_blobs`  (
  `thread_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `checkpoint_ns` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `channel` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `version` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `type` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `blob` longblob NULL,
  `checkpoint_ns_hash` binary(16) NOT NULL,
  PRIMARY KEY (`thread_id`, `checkpoint_ns_hash`, `channel`, `version`) USING BTREE,
  INDEX `checkpoint_blobs_thread_id_idx`(`thread_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for checkpoint_migrations
-- ----------------------------
DROP TABLE IF EXISTS `checkpoint_migrations`;
CREATE TABLE `checkpoint_migrations`  (
  `v` int NOT NULL,
  PRIMARY KEY (`v`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for checkpoint_writes
-- ----------------------------
DROP TABLE IF EXISTS `checkpoint_writes`;
CREATE TABLE `checkpoint_writes`  (
  `thread_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `checkpoint_ns` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `checkpoint_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `task_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `idx` int NOT NULL,
  `channel` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `type` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `blob` longblob NOT NULL,
  `checkpoint_ns_hash` binary(16) NOT NULL,
  `task_path` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  PRIMARY KEY (`thread_id`, `checkpoint_ns_hash`, `checkpoint_id`, `task_id`, `idx`) USING BTREE,
  INDEX `checkpoint_writes_thread_id_idx`(`thread_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for checkpoints
-- ----------------------------
DROP TABLE IF EXISTS `checkpoints`;
CREATE TABLE `checkpoints`  (
  `thread_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `checkpoint_ns` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '',
  `checkpoint_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `parent_checkpoint_id` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `type` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `checkpoint` json NOT NULL,
  `metadata` json NOT NULL,
  `checkpoint_ns_hash` binary(16) NOT NULL,
  PRIMARY KEY (`thread_id`, `checkpoint_ns_hash`, `checkpoint_id`) USING BTREE,
  INDEX `checkpoints_thread_id_idx`(`thread_id` ASC) USING BTREE,
  INDEX `checkpoints_checkpoint_id_idx`(`checkpoint_id` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for events
-- ----------------------------
DROP TABLE IF EXISTS `events`;
CREATE TABLE `events`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `batch_id` bigint UNSIGNED NOT NULL,
  `candidate_id` bigint UNSIGNED NULL DEFAULT NULL COMMENT '批次级事件为空',
  `node_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `event_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'started/completed/retried/reviewed/failed 等',
  `level` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'info',
  `attempt_count` int UNSIGNED NOT NULL DEFAULT 0,
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `details` json NULL COMMENT '规则版本、路由原因等，禁止写入密钥和完整简历',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_event_batch_time`(`batch_id` ASC, `created_at` ASC, `id` ASC) USING BTREE,
  INDEX `idx_event_batch_candidate`(`batch_id` ASC, `candidate_id` ASC) USING BTREE,
  CONSTRAINT `fk_event_batch` FOREIGN KEY (`batch_id`) REFERENCES `batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_event_candidate` FOREIGN KEY (`batch_id`, `candidate_id`) REFERENCES `candidates` (`batch_id`, `id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_event_level` CHECK (`level` in (_utf8mb4'info',_utf8mb4'warning',_utf8mb4'error'))
) ENGINE = InnoDB AUTO_INCREMENT = 1748 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '运行和人工事件，按时间追加' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for file_import_tasks
-- ----------------------------
DROP TABLE IF EXISTS `file_import_tasks`;
CREATE TABLE `file_import_tasks`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `task_id` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '应用生成的唯一任务标识，可用于 LangGraph thread_id',
  `file_id` bigint UNSIGNED NOT NULL,
  `status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending' COMMENT 'pending/running/completed/failed',
  `current_node` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'prepare_import/parse_pdf/parse_word/normalize_content/save_import_result',
  `node_progress` json NULL COMMENT '本次各节点状态、耗时和时间；节点执行后持久化，不保存简历正文',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '本次任务失败原因，不写密钥或简历全文',
  `started_at` datetime(6) NULL DEFAULT NULL,
  `finished_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_import_task_id`(`task_id` ASC) USING BTREE,
  INDEX `idx_import_file_created`(`file_id` ASC, `created_at` ASC, `id` ASC) USING BTREE,
  INDEX `idx_import_status_created`(`status` ASC, `created_at` ASC, `id` ASC) USING BTREE,
  CONSTRAINT `fk_import_task_file` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_import_task_status` CHECK (`status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'completed',_utf8mb4'failed'))
) ENGINE = InnoDB AUTO_INCREMENT = 215 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '简历导入任务与持久化节点进度；不保存岗位评估结果' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for file_pages
-- ----------------------------
DROP TABLE IF EXISTS `file_pages`;
CREATE TABLE `file_pages`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `file_id` bigint UNSIGNED NOT NULL,
  `page_no` int UNSIGNED NOT NULL,
  `text_path` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '逐页 UTF-8 文本路径，相对 backend/storage',
  `text_sha256` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `char_count` int UNSIGNED NOT NULL DEFAULT 0,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_file_page`(`file_id` ASC, `page_no` ASC) USING BTREE,
  CONSTRAINT `fk_page_file` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_page_number` CHECK (`page_no` > 0)
) ENGINE = InnoDB AUTO_INCREMENT = 14 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '按页原文索引，不存 PDF 二进制' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for files
-- ----------------------------
DROP TABLE IF EXISTS `files`;
CREATE TABLE `files`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `sha256` char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `original_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `storage_path` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '相对 backend/storage 的受管路径',
  `size_bytes` bigint UNSIGNED NOT NULL,
  `media_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'application/pdf',
  `file_type` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pdf' COMMENT 'pdf/docx；上传服务根据实际格式写入',
  `parse_status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending' COMMENT 'pending/running/completed/failed',
  `page_count` int UNSIGNED NULL DEFAULT NULL,
  `parse_error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `parsed_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `parser_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '产生当前成功解析结果的解析器，如 pymupdf/mineru/docling',
  `parser_version` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '解析器版本或解析流水线版本，用于判断产物是否可复用',
  `markdown_path` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '原始解析 Markdown 路径；可空，逐页文本仍保留在 file_pages',
  `normalized_markdown_path` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '整理后的 Markdown 路径，不覆盖原始解析内容',
  `source_index_path` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '来源索引 JSON 路径，关联文本片段与原件/预览页码',
  `preview_pdf_path` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'DOCX 转换后的预览 PDF 路径；原件为 PDF 时可空',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_files_sha256`(`sha256` ASC) USING BTREE,
  CONSTRAINT `ck_files_parse` CHECK (`parse_status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'completed',_utf8mb4'failed')),
  CONSTRAINT `ck_files_type` CHECK (`file_type` in (_utf8mb4'pdf',_utf8mb4'docx'))
) ENGINE = InnoDB AUTO_INCREMENT = 213 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'PDF 原件索引，可被不同批次复用' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for job_resumes
-- ----------------------------
DROP TABLE IF EXISTS `job_resumes`;
CREATE TABLE `job_resumes`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `job_id` bigint UNSIGNED NOT NULL,
  `file_id` bigint UNSIGNED NOT NULL,
  `display_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `deleted_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_job_resume_file`(`job_id` ASC, `file_id` ASC) USING BTREE,
  INDEX `idx_job_resume_visible`(`job_id` ASC, `deleted_at` ASC, `id` ASC) USING BTREE,
  INDEX `fk_resume_file`(`file_id` ASC) USING BTREE,
  CONSTRAINT `fk_resume_file` FOREIGN KEY (`file_id`) REFERENCES `files` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_resume_job` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 213 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '岗位简历关联；移除不删除历史评估' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for job_rule_versions
-- ----------------------------
DROP TABLE IF EXISTS `job_rule_versions`;
CREATE TABLE `job_rule_versions`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `job_id` bigint UNSIGNED NOT NULL,
  `version_no` int UNSIGNED NOT NULL,
  `rule_snapshot` json NOT NULL COMMENT '岗位信息与规则完整快照，发布后应用层禁止更新',
  `published_by` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '操作人标识，不依赖账号系统',
  `published_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_rule_job_version`(`job_id` ASC, `version_no` ASC) USING BTREE,
  UNIQUE INDEX `uk_rule_job_id`(`job_id` ASC, `id` ASC) USING BTREE,
  CONSTRAINT `fk_rule_job` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_rule_version` CHECK (`version_no` > 0)
) ENGINE = InnoDB AUTO_INCREMENT = 2 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '不可变岗位发布版本' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for jobs
-- ----------------------------
DROP TABLE IF EXISTS `jobs`;
CREATE TABLE `jobs`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `code` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '稳定业务编码，初始岗位导入去重',
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `responsibilities` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `requirements` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `draft_rules` json NULL COMMENT '硬条件、维度、阈值及排序配置；草稿可未完善',
  `status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'active' COMMENT 'active/disabled',
  `draft_version` int UNSIGNED NOT NULL DEFAULT 1 COMMENT '编辑乐观锁版本',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `deleted_at` datetime(6) NULL DEFAULT NULL COMMENT '软删除时间，保留历史版本和批次',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_jobs_code`(`code` ASC) USING BTREE,
  INDEX `idx_jobs_status_created`(`status` ASC, `created_at` ASC) USING BTREE,
  CONSTRAINT `ck_jobs_status` CHECK (`status` in (_utf8mb4'active',_utf8mb4'disabled'))
) ENGINE = InnoDB AUTO_INCREMENT = 2 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '岗位及可编辑草稿' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for node_executions
-- ----------------------------
DROP TABLE IF EXISTS `node_executions`;
CREATE TABLE `node_executions`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `candidate_id` bigint UNSIGNED NOT NULL,
  `node_name` varchar(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'pending',
  `output_data` json NULL COMMENT '成功节点输出，用于恢复复用；不存完整 PDF',
  `attempt_count` int UNSIGNED NOT NULL DEFAULT 0,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `started_at` datetime(6) NULL DEFAULT NULL,
  `completed_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_node_candidate_name`(`candidate_id` ASC, `node_name` ASC) USING BTREE,
  CONSTRAINT `fk_node_candidate` FOREIGN KEY (`candidate_id`) REFERENCES `candidates` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_node_status` CHECK (`status` in (_utf8mb4'pending',_utf8mb4'running',_utf8mb4'waiting',_utf8mb4'succeeded',_utf8mb4'failed'))
) ENGINE = InnoDB AUTO_INCREMENT = 831 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '节点幂等执行记录，不替代 LangGraph 检查点' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for reservations
-- ----------------------------
DROP TABLE IF EXISTS `reservations`;
CREATE TABLE `reservations`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `batch_id` bigint UNSIGNED NOT NULL,
  `candidate_id` bigint UNSIGNED NOT NULL,
  `slot_id` bigint UNSIGNED NOT NULL,
  `priority_snapshot` json NOT NULL COMMENT '预约时总分、排序维度及其值',
  `preview_version` int UNSIGNED NOT NULL DEFAULT 0,
  `action_preview` json NULL COMMENT '会议参数、时区、人工确认收件人、通知内容',
  `approved_preview_version` int UNSIGNED NULL DEFAULT NULL,
  `approved_preview` json NULL COMMENT '批准时复制完整预览，不允许执行时取未批准新内容',
  `approved_by` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `approved_at` datetime(6) NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_reservation_candidate`(`candidate_id` ASC) USING BTREE,
  UNIQUE INDEX `uk_reservation_slot`(`slot_id` ASC) USING BTREE,
  INDEX `idx_reservation_batch_candidate`(`batch_id` ASC, `candidate_id` ASC) USING BTREE,
  INDEX `idx_reservation_batch_slot`(`batch_id` ASC, `slot_id` ASC) USING BTREE,
  CONSTRAINT `fk_reservation_candidate` FOREIGN KEY (`batch_id`, `candidate_id`) REFERENCES `candidates` (`batch_id`, `id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_reservation_slot` FOREIGN KEY (`batch_id`, `slot_id`) REFERENCES `slots` (`batch_id`, `id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 15 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '成功预约；候补留在 candidates，不占时段' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for reviews
-- ----------------------------
DROP TABLE IF EXISTS `reviews`;
CREATE TABLE `reviews`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `candidate_id` bigint UNSIGNED NOT NULL,
  `operation` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'supplement/approve/defer',
  `review_version` int UNSIGNED NOT NULL COMMENT '操作成功后的版本号',
  `reason` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `supplements` json NULL COMMENT '补充说明与来源，不覆盖模型结果',
  `operator_name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `resume_status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'not_required' COMMENT 'not_required/pending/succeeded/failed',
  `resume_error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_review_candidate_version`(`candidate_id` ASC, `review_version` ASC) USING BTREE,
  CONSTRAINT `fk_review_candidate` FOREIGN KEY (`candidate_id`) REFERENCES `candidates` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_review_operation` CHECK (`operation` in (_utf8mb4'supplement',_utf8mb4'approve',_utf8mb4'defer')),
  CONSTRAINT `ck_review_resume` CHECK (`resume_status` in (_utf8mb4'not_required',_utf8mb4'pending',_utf8mb4'succeeded',_utf8mb4'failed'))
) ENGINE = InnoDB AUTO_INCREMENT = 15 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '人工审核历史及恢复状态，追加写入' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for slots
-- ----------------------------
DROP TABLE IF EXISTS `slots`;
CREATE TABLE `slots`  (
  `id` bigint UNSIGNED NOT NULL AUTO_INCREMENT,
  `batch_id` bigint UNSIGNED NOT NULL,
  `starts_at` datetime(6) NOT NULL COMMENT 'UTC',
  `ends_at` datetime(6) NOT NULL COMMENT 'UTC，每次 45 分钟',
  `timezone` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'Asia/Shanghai' COMMENT '展示用 IANA 时区',
  `interviewer` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_slot_batch_id`(`batch_id` ASC, `id` ASC) USING BTREE,
  INDEX `idx_slot_time`(`starts_at` ASC, `ends_at` ASC) USING BTREE,
  CONSTRAINT `fk_slot_batch` FOREIGN KEY (`batch_id`) REFERENCES `batches` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `ck_slot_duration` CHECK (`ends_at` > `starts_at`)
) ENGINE = InnoDB AUTO_INCREMENT = 15 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '实际面试时段，批次默认配置四个' ROW_FORMAT = Dynamic;

SET FOREIGN_KEY_CHECKS = 1;
