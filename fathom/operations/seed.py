"""First-boot seeding: restore an operator-supplied bundle into an empty database.

`FATHOM_SEED_BUNDLE_URI` names a snapshot (RFC 0002 section 8.1): a git remote,
an exchange-form bundle, or a `.tar.gz` of the repository form. Seeding is a
restore, so it pins the library revision the manifest names and stores the
organization objects in one step. It is idempotent because restore refuses a
database that already holds organization objects: a second boot, a second task,
or the same bundle again changes nothing. A different bundle against a seeded
database is also skipped; later changes go through the API or a new restore
into a new database.
"""

import logging

from fathom.access import ActorKind, Principal, Role
from fathom.errors import Conflict
from fathom.operations.records import Job
from fathom.operations.restore import RestoreRequest, RestoreService

log = logging.getLogger("fathom.seed")

SEEDER = Principal(
    "party--fathom-seed", "organization", ActorKind.SERVICE, frozenset({Role.ADMINISTRATOR})
)


async def seed_organization(restore: RestoreService, uri: str) -> Job | None:
    """The restore job, or None when the database is already seeded."""
    try:
        job = await restore.restore(SEEDER, RestoreRequest(url=uri))
    except Conflict:
        log.info("seed bundle skipped: the database already holds organization objects")
        return None
    log.info("seed bundle %s queued as job %s", uri, job.id)
    return job
