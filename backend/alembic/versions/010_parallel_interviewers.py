"""Allow different interviewers to start interviews at the same time."""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("uk_slot_batch_start", table_name="slots")


def downgrade():
    op.create_index("uk_slot_batch_start", "slots", ["batch_id", "starts_at"], unique=True)
