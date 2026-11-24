"""Query source definitions (RFC 0006).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("integration_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("body", JSONB, nullable=False),
    )
    op.create_index("queries_source", "queries", ["integration_id", "name", "version"], unique=True)


def downgrade() -> None:
    op.drop_index("queries_source", table_name="queries")
    op.drop_table("queries")
