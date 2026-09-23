import hmac
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pine import __version__
from pine.api import health
from pine.config import get_settings
from pine.errors import error_body, register_error_handlers
from pine.logging import configure_logging, request_id_ctx

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
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
        provided = request.headers.get("X-API-Key") or ""
        if (
            key
            and path.startswith("/api/")
            and not path.endswith("/health")
            and not hmac.compare_digest(provided, key)
        ):
            return JSONResponse(
                status_code=401,
                content=error_body("UNAUTHORIZED", "Missing or invalid API key"),
            )
        return await call_next(request)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
        )
        return response

    register_error_handlers(app)
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
