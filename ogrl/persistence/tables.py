"""The organization database schema (RFC 0003 section 7).

Each object is stored as its JSON in a `jsonb` column. The columns beside it
are derived from the object and written with it. These table definitions are
the reference the Alembic migrations are reviewed against; the application
never creates tables itself.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

# The current revision of every object the database has ever held. A row is
# never deleted: a revoked id stays so references resolve and it is never reused.
objects = Table(
    "objects",
    metadata,
    Column("id", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("source", Text, nullable=False),  # library | provider:<bundle id> | organization
    Column("modified", DateTime(timezone=True), nullable=False),
    Column("revoked", Boolean, nullable=False, server_default="false"),
    Column("body", JSONB, nullable=False),
    Index("objects_type_id", "type", "id"),
    Index("objects_source", "source"),
)

# Every revision of every object, with who wrote it and when the store took it
# (RFC 0002 section 4). Status at a past instant reads the latest revision of
# each object whose `stored_at` is at or before that instant.
revisions = Table(
    "revisions",
    metadata,
    Column("seq", BigInteger, Identity(), primary_key=True),
    Column("object_id", Text, nullable=False),
    Column("stored_at", DateTime(timezone=True), nullable=False),
    Column("source", Text, nullable=False),
    Column("writer", Text, nullable=False),
    Column("body", JSONB, nullable=False),
    Index("revisions_object_stored", "object_id", "stored_at"),
    Index("revisions_stored", "stored_at"),
)

provider_pins = Table(
    "provider_pins",
    metadata,
    Column("id", Text, primary_key=True),
    Column("body", JSONB, nullable=False),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created", DateTime(timezone=True), nullable=False),
    Column("claimed_by", Text),
    Column("body", JSONB, nullable=False),
    Index("jobs_created", "created"),
)

settings = Table(
    "settings",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
)

# One row. `version` advances on every object write, so a process can tell
# whether its cached graph is current with one query.
store_state = Table(
    "store_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("version", BigInteger, nullable=False, server_default="0"),
    Column("history_start", DateTime(timezone=True)),
    Column("library_pin", JSONB),
)

# --- Interactive auth: OIDC identities, browser sessions, and minted API tokens ---

auth_identities = Table(
    "auth_identities",
    metadata,
    Column("actor_id", Text, primary_key=True),
    Column("issuer", Text),
    Column("subject", Text),
    Column("email", Text),
    Column("kind", Text, nullable=False, server_default="person"),
    Column("roles", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("auth_identities_issuer_subject", "issuer", "subject", unique=True),
)

auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("token_digest", Text, primary_key=True),
    Column("actor_id", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Index("auth_sessions_actor", "actor_id"),
)

auth_tokens = Table(
    "auth_tokens",
    metadata,
    Column("token_digest", Text, primary_key=True),
    Column("id", Text, nullable=False, unique=True),
    Column("actor_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("created_by_ref", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    Column("last_used_at", DateTime(timezone=True)),
    Index("auth_tokens_actor", "actor_id"),
)

# --- Integrations (RFC 0005): connections and snapshot rows. Not RFC 0001 objects. ---

connections = Table(
    "connections",
    metadata,
    Column("id", Text, primary_key=True),
    Column("integration_id", Text, nullable=False),
    Column("modified", DateTime(timezone=True), nullable=False),
    Column("body", JSONB, nullable=False),
    Index("connections_integration", "integration_id"),
)

snapshots = Table(
    "snapshots",
    metadata,
    Column("id", Text, primary_key=True),
    Column("connection_id", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("collected", DateTime(timezone=True), nullable=False),
    Column("complete", Boolean, nullable=False),
    Column("body", JSONB, nullable=False),
    Index("snapshots_connection_source_collected", "connection_id", "source", "collected"),
)

integration_installs = Table(
    "integration_installs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("version", Text, primary_key=True),
    Column("enabled", Boolean, nullable=False, server_default="false"),
    Column("installed", DateTime(timezone=True), nullable=False),
    Column("body", JSONB, nullable=False),
)
