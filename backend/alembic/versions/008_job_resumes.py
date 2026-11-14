"""Per-job resume workspace and historical associations."""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE job_resumes (\n    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,\n    job_id BIGINT UNSIGNED NOT NULL,\n    file_id BIGINT UNSIGNED NOT NULL,\n    display_name VARCHAR(255) NOT NULL,\n    deleted_at DATETIME(6) NULL,\n    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),\n    PRIMARY KEY (id),\n    UNIQUE KEY uk_job_resume_file (job_id, file_id),\n    KEY idx_job_resume_visible (job_id, deleted_at, id),\n    CONSTRAINT fk_resume_job FOREIGN KEY (job_id) REFERENCES jobs (id),\n    CONSTRAINT fk_resume_file FOREIGN KEY (file_id) REFERENCES files (id)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='岗位简历关联；移除不删除历史评估';"
    )
    op.execute(
        "INSERT INTO job_resumes (job_id, file_id, display_name)\nSELECT b.job_id, c.file_id, MIN(c.original_filename)\nFROM candidates c JOIN batches b ON b.id = c.batch_id\nLEFT JOIN job_resumes r ON r.job_id = b.job_id AND r.file_id = c.file_id\nWHERE r.id IS NULL\nGROUP BY b.job_id, c.file_id;"
    )


def downgrade():
    op.drop_table("job_resumes")
