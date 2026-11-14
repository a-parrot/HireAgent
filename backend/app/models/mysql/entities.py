"""Business ORM models aligned with sql/01-schema.sql."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME
from sqlalchemy.dialects.mysql import INTEGER as MYSQL_INTEGER

from app.models.mysql.base import Base


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


UInt = MYSQL_INTEGER(unsigned=True).with_variant(Integer, "sqlite")
Timestamp = MYSQL_DATETIME(fsp=6).with_variant(DateTime, "sqlite")
ID = BIGINT(unsigned=True).with_variant(Integer, "sqlite")


class Job(Base):
    __tablename__ = "jobs"
    id = Column(ID, primary_key=True, autoincrement=True)
    code = Column(String(64), nullable=False)
    name = Column(String(200), nullable=False)
    responsibilities = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    draft_rules = Column(JSON, nullable=True)
    status = Column(String(16), nullable=False, default="active")
    draft_version = Column(UInt, nullable=False, default=1)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("code", name="uk_jobs_code"),
        Index("idx_jobs_status_created", "status", "created_at"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_jobs_status"),
    )


class JobRuleVersion(Base):
    __tablename__ = "job_rule_versions"
    id = Column(ID, primary_key=True, autoincrement=True)
    job_id = Column(ID, nullable=False)
    version_no = Column(UInt, nullable=False)
    rule_snapshot = Column(JSON, nullable=False)
    published_by = Column(String(128), nullable=True)
    published_at = Column(Timestamp, nullable=False, default=utcnow)
    __table_args__ = (
        UniqueConstraint("job_id", "version_no", name="uk_rule_job_version"),
        UniqueConstraint("job_id", "id", name="uk_rule_job_id"),
        ForeignKeyConstraint(["job_id"], ["jobs.id"], name="fk_rule_job"),
        CheckConstraint("version_no > 0", name="ck_rule_version"),
    )


class File(Base):
    __tablename__ = "files"
    id = Column(ID, primary_key=True, autoincrement=True)
    sha256 = Column(String(64), nullable=False)
    original_name = Column(String(255), nullable=False)
    storage_path = Column(String(1024), nullable=False)
    size_bytes = Column(ID, nullable=False)
    media_type = Column(String(100), nullable=False, default="application/pdf")
    parse_status = Column(String(16), nullable=False, default="pending")
    page_count = Column(UInt, nullable=True)
    parse_error = Column(Text, nullable=True)
    parsed_at = Column(Timestamp, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("sha256", name="uk_files_sha256"),
        CheckConstraint(
            "parse_status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_files_parse",
        ),
    )


class FilePage(Base):
    __tablename__ = "file_pages"
    id = Column(ID, primary_key=True, autoincrement=True)
    file_id = Column(ID, nullable=False)
    page_no = Column(UInt, nullable=False)
    text_path = Column(String(1024), nullable=False)
    text_sha256 = Column(String(64), nullable=False)
    char_count = Column(UInt, nullable=False, default=0)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    __table_args__ = (
        UniqueConstraint("file_id", "page_no", name="uk_file_page"),
        ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_page_file"),
        CheckConstraint("page_no > 0", name="ck_page_number"),
    )


class Batch(Base):
    __tablename__ = "batches"
    id = Column(ID, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    job_id = Column(ID, nullable=False)
    rule_version_id = Column(ID, nullable=False)
    rule_snapshot = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default="pending")
    started_at = Column(Timestamp, nullable=True)
    evaluation_completed_at = Column(Timestamp, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        Index("idx_batches_created", "created_at"),
        Index("idx_batches_status", "status"),
        ForeignKeyConstraint(
            ["job_id", "rule_version_id"],
            ["job_rule_versions.job_id", "job_rule_versions.id"],
            name="fk_batch_rule",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'evaluation_done')",
            name="ck_batch_status",
        ),
    )


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(ID, primary_key=True, autoincrement=True)
    batch_id = Column(ID, nullable=False)
    file_id = Column(ID, nullable=False)
    original_filename = Column(String(255), nullable=False)
    workflow_id = Column(String(64), nullable=False)
    name = Column(String(200), nullable=True)
    contact_info = Column(JSON, nullable=True)
    processing_status = Column(String(24), nullable=False, default="pending")
    current_node = Column(String(64), nullable=True)
    checkpoint_id = Column(String(128), nullable=True)
    extracted_facts = Column(JSON, nullable=True)
    evidence = Column(JSON, nullable=True)
    hard_conditions = Column(JSON, nullable=True)
    dimension_scores = Column(JSON, nullable=True)
    total_score = Column(Numeric(5, 2), nullable=True)
    recommendation = Column(String(24), nullable=True)
    missing_fields = Column(JSON, nullable=True)
    risks = Column(JSON, nullable=True)
    review_notes = Column(JSON, nullable=True)
    needs_human_review = Column(Boolean, nullable=False, default=False)
    model_id = Column(String(200), nullable=True)
    prompt_versions = Column(JSON, nullable=True)
    review_status = Column(String(16), nullable=False, default="pending")
    review_version = Column(UInt, nullable=False, default=0)
    schedule_status = Column(String(16), nullable=False, default="unscheduled")
    waitlist_reason = Column(Text, nullable=True)
    retry_count = Column(UInt, nullable=False, default=0)
    error_node = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(Timestamp, nullable=True)
    completed_at = Column(Timestamp, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("batch_id", "file_id", name="uk_candidate_batch_file"),
        UniqueConstraint("workflow_id", name="uk_candidate_workflow"),
        UniqueConstraint("batch_id", "id", name="uk_candidate_batch_id"),
        Index("idx_candidate_batch_status", "batch_id", "processing_status"),
        Index("idx_candidate_batch_review", "batch_id", "review_status"),
        Index("idx_candidate_batch_score", "batch_id", "total_score"),
        ForeignKeyConstraint(["batch_id"], ["batches.id"], name="fk_candidate_batch"),
        ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_candidate_file"),
        CheckConstraint(
            "processing_status IN ('pending', 'running', 'waiting_review', 'completed', 'failed')",
            name="ck_candidate_processing",
        ),
        CheckConstraint(
            "total_score IS NULL OR total_score BETWEEN 0 AND 100",
            name="ck_candidate_score",
        ),
        CheckConstraint(
            "recommendation IS NULL OR recommendation IN ('recommended', 'needs_review', 'deferred')",
            name="ck_candidate_recommendation",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'deferred')",
            name="ck_candidate_review",
        ),
        CheckConstraint(
            "schedule_status IN ('unscheduled', 'scheduled', 'waitlisted')",
            name="ck_candidate_schedule",
        ),
    )


class Review(Base):
    __tablename__ = "reviews"
    id = Column(ID, primary_key=True, autoincrement=True)
    candidate_id = Column(ID, nullable=False)
    operation = Column(String(16), nullable=False)
    review_version = Column(UInt, nullable=False)
    reason = Column(Text, nullable=False)
    supplements = Column(JSON, nullable=True)
    operator_name = Column(String(128), nullable=False)
    resume_status = Column(String(16), nullable=False, default="not_required")
    resume_error = Column(Text, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "candidate_id", "review_version", name="uk_review_candidate_version"
        ),
        ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_review_candidate"
        ),
        CheckConstraint(
            "operation IN ('supplement', 'approve', 'defer')",
            name="ck_review_operation",
        ),
        CheckConstraint(
            "resume_status IN ('not_required', 'pending', 'succeeded', 'failed')",
            name="ck_review_resume",
        ),
    )


class Slot(Base):
    __tablename__ = "slots"
    id = Column(ID, primary_key=True, autoincrement=True)
    batch_id = Column(ID, nullable=False)
    starts_at = Column(Timestamp, nullable=False)
    ends_at = Column(Timestamp, nullable=False)
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    interviewer = Column(String(200), nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("batch_id", "id", name="uk_slot_batch_id"),
        UniqueConstraint("batch_id", "starts_at", name="uk_slot_batch_start"),
        Index("idx_slot_time", "starts_at", "ends_at"),
        ForeignKeyConstraint(["batch_id"], ["batches.id"], name="fk_slot_batch"),
        CheckConstraint(
            "ends_at = DATE_ADD(starts_at, INTERVAL 45 MINUTE)", name="ck_slot_duration"
        ).ddl_if(dialect="mysql"),
    )


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(ID, primary_key=True, autoincrement=True)
    batch_id = Column(ID, nullable=False)
    candidate_id = Column(ID, nullable=False)
    slot_id = Column(ID, nullable=False)
    priority_snapshot = Column(JSON, nullable=False)
    preview_version = Column(UInt, nullable=False, default=0)
    action_preview = Column(JSON, nullable=True)
    approved_preview_version = Column(UInt, nullable=True)
    approved_preview = Column(JSON, nullable=True)
    approved_by = Column(String(128), nullable=True)
    approved_at = Column(Timestamp, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uk_reservation_candidate"),
        UniqueConstraint("slot_id", name="uk_reservation_slot"),
        Index("idx_reservation_batch_candidate", "batch_id", "candidate_id"),
        Index("idx_reservation_batch_slot", "batch_id", "slot_id"),
        ForeignKeyConstraint(
            ["batch_id", "candidate_id"],
            ["candidates.batch_id", "candidates.id"],
            name="fk_reservation_candidate",
        ),
        ForeignKeyConstraint(
            ["batch_id", "slot_id"],
            ["slots.batch_id", "slots.id"],
            name="fk_reservation_slot",
        ),
    )


class ActionRecord(Base):
    __tablename__ = "action_records"
    id = Column(ID, primary_key=True, autoincrement=True)
    reservation_id = Column(ID, nullable=False)
    action_type = Column(String(16), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    status = Column(String(24), nullable=False, default="not_executed")
    provider = Column(String(100), nullable=True)
    approved_preview_version = Column(UInt, nullable=True)
    request_snapshot = Column(JSON, nullable=True)
    response_data = Column(JSON, nullable=True)
    external_id = Column(String(255), nullable=True)
    meeting_url = Column(Text, nullable=True)
    attempt_count = Column(UInt, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    started_at = Column(Timestamp, nullable=True)
    completed_at = Column(Timestamp, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "reservation_id", "action_type", name="uk_action_reservation_type"
        ),
        UniqueConstraint("idempotency_key", name="uk_action_idempotency"),
        Index("idx_action_status", "status", "updated_at"),
        ForeignKeyConstraint(
            ["reservation_id"], ["reservations.id"], name="fk_action_reservation"
        ),
        CheckConstraint(
            "action_type IN ('meeting', 'notification')", name="ck_action_type"
        ),
        CheckConstraint(
            "status IN ('not_configured', 'not_executed', 'running', 'succeeded', 'failed', 'uncertain')",
            name="ck_action_status",
        ),
    )


class NodeExecution(Base):
    __tablename__ = "node_executions"
    id = Column(ID, primary_key=True, autoincrement=True)
    candidate_id = Column(ID, nullable=False)
    node_name = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    output_data = Column(JSON, nullable=True)
    attempt_count = Column(UInt, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(Timestamp, nullable=True)
    completed_at = Column(Timestamp, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    updated_at = Column(Timestamp, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint("candidate_id", "node_name", name="uk_node_candidate_name"),
        ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="fk_node_candidate"
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'waiting', 'succeeded', 'failed')",
            name="ck_node_status",
        ),
    )


class Event(Base):
    __tablename__ = "events"
    id = Column(ID, primary_key=True, autoincrement=True)
    batch_id = Column(ID, nullable=False)
    candidate_id = Column(ID, nullable=True)
    node_name = Column(String(64), nullable=True)
    event_type = Column(String(32), nullable=False)
    level = Column(String(8), nullable=False, default="info")
    attempt_count = Column(UInt, nullable=False, default=0)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(Timestamp, nullable=False, default=utcnow)
    __table_args__ = (
        Index("idx_event_batch_time", "batch_id", "created_at", "id"),
        Index("idx_event_batch_candidate", "batch_id", "candidate_id"),
        ForeignKeyConstraint(["batch_id"], ["batches.id"], name="fk_event_batch"),
        ForeignKeyConstraint(
            ["batch_id", "candidate_id"],
            ["candidates.batch_id", "candidates.id"],
            name="fk_event_candidate",
        ),
        CheckConstraint("level IN ('info', 'warning', 'error')", name="ck_event_level"),
    )
