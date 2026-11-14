"""Hide deleted jobs without removing version and batch history."""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True))


def downgrade():
    op.drop_column("jobs", "deleted_at")
