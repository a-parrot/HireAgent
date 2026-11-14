-- 一次性增量升级；先执行 04-resume-import.sql。已有表时不要重复执行。
USE hireagent;
CREATE TABLE job_resumes (
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

-- 导入历史批次中的岗位简历关联，保留原候选人及批次。
INSERT INTO job_resumes (job_id, file_id, display_name)
SELECT b.job_id, c.file_id, MIN(c.original_filename)
FROM candidates c JOIN batches b ON b.id = c.batch_id
LEFT JOIN job_resumes r ON r.job_id = b.job_id AND r.file_id = c.file_id
WHERE r.id IS NULL
GROUP BY b.job_id, c.file_id;
