from fastapi import APIRouter, FastAPI

from ogrl import telemetry
from ogrl.api import paths, problems
from ogrl.api.handlers import auth, meta, objects, views
from ogrl.api.paths.meta import Health
from ogrl.api.registrar import Registrar
from ogrl.container import Container


def create_app(container: Container) -> FastAPI:
    app = FastAPI(
        title="OGRL API",
        version=container.version,
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )
    problems.install(app)

    # Root health probe for ALB TargetGroup (deploy/aws/template.yaml) and Next.js /health rewrite.
    @app.get("/health", include_in_schema=False)
    async def root_health() -> Health:
        return Health(status="ok", version=container.version)

    router = APIRouter(prefix="/v1")
    registrar = Registrar(
        router,
        container.authenticator,
        container.authorizer,
        container.features,
        allowed_origins=container.allowed_origins,
    )

    meta.register(registrar, container.version)
    auth.register(registrar, container.auth)
    for collection in paths.collections.ALL_COLLECTIONS:
        objects.register_collection(registrar, container.objects, collection)
    views.register(registrar, container)

    registrar.require_complete(paths.all_endpoints())
    app.include_router(router)  # after registration: include_router copies routes
    telemetry.instrument_app(app)
    return app
