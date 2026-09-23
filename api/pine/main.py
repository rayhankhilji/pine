from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pine import __version__
from pine.api import health
from pine.config import get_settings
from pine.errors import error_body, register_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pine API", version=__version__)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        key = settings.PINE_API_KEY
        path = request.url.path
        protected = key and path.startswith("/api/") and not path.endswith("/health")
        if protected and request.headers.get("X-API-Key") != key:
            return JSONResponse(
                status_code=401,
                content=error_body("UNAUTHORIZED", "Missing or invalid API key"),
            )
        return await call_next(request)

    register_error_handlers(app)
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
