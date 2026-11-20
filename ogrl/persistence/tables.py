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
