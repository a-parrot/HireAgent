"""Allow manually adjusted interview slot durations."""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE slots DROP CHECK ck_slot_duration, ADD CONSTRAINT ck_slot_duration CHECK (ends_at > starts_at)"
    )


def downgrade():
    # MySQL rejects this change if adjustable-duration slots still exist.
    op.execute(
        "ALTER TABLE slots DROP CHECK ck_slot_duration, ADD CONSTRAINT ck_slot_duration CHECK (ends_at = DATE_ADD(starts_at, INTERVAL 45 MINUTE))"
    )
