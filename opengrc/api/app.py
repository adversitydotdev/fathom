from fastapi import APIRouter, FastAPI

from opengrc.api import paths, problems
from opengrc.api.handlers import meta, objects, views
from opengrc.api.registrar import Registrar
from opengrc.container import Container


def create_app(container: Container) -> FastAPI:
    app = FastAPI(
        title="OpenGRC API",
        version=container.version,
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )
    problems.install(app)

    router = APIRouter(prefix="/v1")
    registrar = Registrar(router, container.authenticator, container.authorizer, container.features)

    meta.register(registrar, container.version)
    for collection in paths.collections.ALL_COLLECTIONS:
        objects.register_collection(registrar, container.objects, collection)
    views.register(registrar, container)

    registrar.require_complete(paths.all_endpoints())
    app.include_router(router)  # after registration: include_router copies routes
    return app
