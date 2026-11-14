"""Independent resume import metadata and persistent progress."""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE files\n    ADD COLUMN file_type VARCHAR(16) NOT NULL DEFAULT 'pdf'\n        COMMENT 'pdf/docx；上传服务根据实际格式写入' AFTER media_type,\n    ADD COLUMN parser_name VARCHAR(64) NULL\n        COMMENT '产生当前成功解析结果的解析器，如 pymupdf/mineru/docling',\n    ADD COLUMN parser_version VARCHAR(128) NULL\n        COMMENT '解析器版本或解析流水线版本，用于判断产物是否可复用',\n    ADD COLUMN markdown_path VARCHAR(1024) NULL\n        COMMENT '原始解析 Markdown 路径；可空，逐页文本仍保留在 file_pages',\n    ADD COLUMN normalized_markdown_path VARCHAR(1024) NULL\n        COMMENT '整理后的 Markdown 路径，不覆盖原始解析内容',\n    ADD COLUMN source_index_path VARCHAR(1024) NULL\n        COMMENT '来源索引 JSON 路径，关联文本片段与原件/预览页码',\n    ADD COLUMN preview_pdf_path VARCHAR(1024) NULL\n        COMMENT 'DOCX 转换后的预览 PDF 路径；原件为 PDF 时可空',\n    ADD CONSTRAINT ck_files_type CHECK (file_type IN ('pdf', 'docx'));"
    )
    op.execute(
        "CREATE TABLE file_import_tasks (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    task_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL\n        COMMENT '应用生成的唯一任务标识，可用于 LangGraph thread_id',\n    file_id BIGINT UNSIGNED NOT NULL,\n    status VARCHAR(16) NOT NULL DEFAULT 'pending'\n        COMMENT 'pending/running/completed/failed',\n    current_node VARCHAR(64) NULL\n        COMMENT 'prepare_import/parse_pdf/parse_word/normalize_content/save_import_result',\n    node_progress JSON NULL\n        COMMENT '本次各节点状态、耗时和时间；节点执行后持久化，不保存简历正文',\n    error_message TEXT NULL COMMENT '本次任务失败原因，不写密钥或简历全文',\n    started_at DATETIME(6) NULL,\n    finished_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)\n        ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_import_task_id (task_id),\n    KEY idx_import_file_created (file_id, created_at, id),\n    KEY idx_import_status_created (status, created_at, id),\n    CONSTRAINT fk_import_task_file FOREIGN KEY (file_id) REFERENCES files (id),\n    CONSTRAINT ck_import_task_status\n        CHECK (status IN ('pending', 'running', 'completed', 'failed'))\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci\n    COMMENT='简历导入任务与持久化节点进度；不保存岗位评估结果';"
    )


def downgrade():
    op.drop_table("file_import_tasks")
    op.drop_constraint("ck_files_type", "files", type_="check")
    for column in [
        "preview_pdf_path",
        "source_index_path",
        "normalized_markdown_path",
        "markdown_path",
        "parser_version",
        "parser_name",
        "file_type",
    ]:
        op.drop_column("files", column)
