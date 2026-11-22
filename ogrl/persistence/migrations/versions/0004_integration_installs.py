"""Installed integration archive versions (RFC 0005 section 4).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_installs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("version", sa.Text, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("installed", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body", JSONB, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("integration_installs")
