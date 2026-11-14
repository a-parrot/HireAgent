-- HireAgent 简历独立导入流程：MySQL 8.4 增量升级。
-- 供 SQL 初始化的旧库人工升级；对应 Alembic 007，两种入口不要重复执行。
-- 本文件不会自动运行；自定义库名时修改 USE。
-- 前置：已有 files 表（01-schema.sql）。本脚本不修改岗位、评分规则或评估结果。
-- 一次性执行：先确认以下新增列和 file_import_tasks 表均不存在。
-- MySQL DDL 隐式提交，不能用事务整体回滚；中途失败后先检查结构，不要直接重跑。
USE hireagent;
SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- 1. 文件类型、解析器信息和解析产物。
-- 现有系统仅接收 PDF，因此旧数据默认 pdf；后续上传 DOCX 时应用必须显式写 docx。
-- 所有产物路径均为相对 backend/storage 的受管路径，不保存服务器绝对路径。
-- 旧解析结果保持原状态，新增产物和解析器字段为 NULL；不强制历史文件重新解析。
ALTER TABLE files
    ADD COLUMN file_type VARCHAR(16) NOT NULL DEFAULT 'pdf'
        COMMENT 'pdf/docx；上传服务根据实际格式写入' AFTER media_type,
    ADD COLUMN parser_name VARCHAR(64) NULL
        COMMENT '产生当前成功解析结果的解析器，如 pymupdf/mineru/docling',
    ADD COLUMN parser_version VARCHAR(128) NULL
        COMMENT '解析器版本或解析流水线版本，用于判断产物是否可复用',
    ADD COLUMN markdown_path VARCHAR(1024) NULL
        COMMENT '原始解析 Markdown 路径；可空，逐页文本仍保留在 file_pages',
    ADD COLUMN normalized_markdown_path VARCHAR(1024) NULL
        COMMENT '整理后的 Markdown 路径，不覆盖原始解析内容',
    ADD COLUMN source_index_path VARCHAR(1024) NULL
        COMMENT '来源索引 JSON 路径，关联文本片段与原件/预览页码',
    ADD COLUMN preview_pdf_path VARCHAR(1024) NULL
        COMMENT 'DOCX 转换后的预览 PDF 路径；原件为 PDF 时可空',
    ADD CONSTRAINT ck_files_type CHECK (file_type IN ('pdf', 'docx'));

-- 2. 独立导入任务：每次实际重试创建新任务，保留上一轮执行记录。
-- 同一文件可用于多个招聘批次，任务只绑定 file_id，不绑定岗位或评分规则。
-- 任务状态与 files.parse_status 使用同一组状态；completed 仅表示可进入评估。
CREATE TABLE file_import_tasks (
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

-- 应用实现约定（SQL 本身不启动导入，也不提供自动重试）：
-- 1. 认领任务时锁定 files 行，检查已有 pending/running 任务，防止重复解析同一文件。
-- 2. 只有产物和来源索引保存成功后，才将文件与任务标为 completed。
-- 3. 服务重启后核实遗留 running 任务并标记可重试，不能仅凭内存状态显示成功。
-- 4. file_pages 继续保存逐页文本；DOCX 页码基于转换后的预览 PDF，不能虚构原件页码。
-- 5. 对应 ORM、导入服务及 Alembic 007 已实现；不要在执行此脚本后重复运行 007。

-- 执行后可只读核对：
-- SHOW COLUMNS FROM files;
-- SHOW CREATE TABLE file_import_tasks;
-- SELECT file_type, COUNT(*) FROM files GROUP BY file_type;
