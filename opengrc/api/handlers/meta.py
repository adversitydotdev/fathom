from opengrc.api import paths
from opengrc.api.paths.meta import Health
from opengrc.api.registrar import Registrar


def register(registrar: Registrar, version: str) -> None:
    async def health() -> Health:
        return Health(status="ok", version=version)

    registrar.handle(paths.meta.GET_HEALTH, health)
