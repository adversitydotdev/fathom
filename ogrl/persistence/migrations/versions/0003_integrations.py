"""Integration connections and snapshot rows (RFC 0005).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("integration_id", sa.Text, nullable=False),
        sa.Column("modified", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", JSONB, nullable=False),
    )
    op.create_index("connections_integration", "connections", ["integration_id"])
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("connection_id", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("collected", sa.DateTime(timezone=True), nullable=False),
        sa.Column("complete", sa.Boolean, nullable=False),
        sa.Column("body", JSONB, nullable=False),
    )
    op.create_index(
        "snapshots_connection_source_collected",
        "snapshots",
        ["connection_id", "source", "collected"],
    )


def downgrade() -> None:
    op.drop_index("snapshots_connection_source_collected", table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index("connections_integration", table_name="connections")
    op.drop_table("connections")
