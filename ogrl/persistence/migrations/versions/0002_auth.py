"""Interactive authentication tables: OIDC identities, sessions, and minted API tokens.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("actor_id", sa.Text, primary_key=True),
        sa.Column("issuer", sa.Text),
        sa.Column("subject", sa.Text),
        sa.Column("email", sa.Text),
        sa.Column("kind", sa.Text, nullable=False, server_default="person"),
        sa.Column("roles", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "auth_identities_issuer_subject", "auth_identities", ["issuer", "subject"], unique=True
    )

    op.create_table(
        "auth_sessions",
        sa.Column("token_digest", sa.Text, primary_key=True),
        sa.Column("actor_id", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("auth_sessions_actor", "auth_sessions", ["actor_id"])

    op.create_table(
        "auth_tokens",
        sa.Column("token_digest", sa.Text, primary_key=True),
        sa.Column("id", sa.Text, nullable=False, unique=True),
        sa.Column("actor_id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_by_ref", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("auth_tokens_actor", "auth_tokens", ["actor_id"])


def downgrade() -> None:
    for table in ("auth_tokens", "auth_sessions", "auth_identities"):
        op.drop_table(table)
