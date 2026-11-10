"""In-memory stores for tests and local runs. Postgres implements the same protocols."""

from datetime import datetime

from opengrc.errors import Conflict, PreconditionFailed
from opengrc.kernel.models import Control
from opengrc.operations.controls import ControlQuery


class MemoryControls:
    def __init__(self, seed: list[Control] | None = None) -> None:
        self._rows: dict[str, Control] = {c.id: c for c in seed or []}

    async def get(self, control_id: str) -> Control | None:
        return self._rows.get(control_id)

    async def page(self, query: ControlQuery) -> tuple[list[Control], str | None]:
        rows = sorted(self._rows.values(), key=lambda c: c.id)
        rows = [
            c
            for c in rows
            if (query.revoked or not c.revoked)
            and (query.origin is None or c.origin == query.origin)
            and (query.family is None or c.family == query.family)
            and (query.q is None or query.q.lower() in f"{c.name} {c.statement}".lower())
            and (query.cursor is None or c.id > query.cursor)
        ]
        page = rows[: query.limit]
        next_cursor = page[-1].id if len(rows) > query.limit else None
        return page, next_cursor

    async def insert(self, control: Control) -> None:
        if control.id in self._rows:
            raise Conflict(f"id {control.id} is in use", slug="id-taken")
        self._rows[control.id] = control

    async def replace(self, control: Control, expected_modified: datetime) -> None:
        current = self._rows.get(control.id)
        if current is None or current.modified != expected_modified:
            raise PreconditionFailed("object changed since it was read")
        self._rows[control.id] = control
