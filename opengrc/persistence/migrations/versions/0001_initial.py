"""The organization database: objects, revisions, pins, jobs, settings.

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "objects",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("modified", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("body", JSONB, nullable=False),
    )
    op.create_index("objects_type_id", "objects", ["type", "id"])
    op.create_index("objects_source", "objects", ["source"])

    op.create_table(
        "revisions",
        sa.Column("seq", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("object_id", sa.Text, nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("writer", sa.Text, nullable=False),
        sa.Column("body", JSONB, nullable=False),
    )
    op.create_index("revisions_object_stored", "revisions", ["object_id", "stored_at"])
    op.create_index("revisions_stored", "revisions", ["stored_at"])

    op.create_table(
        "provider_pins",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("body", JSONB, nullable=False),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by", sa.Text),
        sa.Column("body", JSONB, nullable=False),
    )
    op.create_index("jobs_created", "jobs", ["created"])

    op.create_table(
        "settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )

    op.create_table(
        "store_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("history_start", sa.DateTime(timezone=True)),
        sa.Column("library_pin", JSONB),
    )
    op.execute("INSERT INTO store_state (id, version) VALUES (1, 0)")


def downgrade() -> None:
    for table in ("store_state", "settings", "jobs", "provider_pins", "revisions", "objects"):
        op.drop_table(table)
