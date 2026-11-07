"""The FastAPI application (D-32).

Run locally from backend/:

    uvicorn app.main:create_app --factory --reload

`create_app` builds the app from settings, so tests can build one with test settings.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api import auth, health
from app.api.errors import error_response, register_error_handlers
from app.api.security import OriginCheckMiddleware
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, exception_fields, request_id_var, safe_request_id
from app.db.session import create_db_engine

logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request id, access log line, and the last-resort 500 (A-64, A-66).

    Unexpected errors are turned into the standard error body here, inside the request's
    context, so the response and the log line carry the same request id."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = safe_request_id(request.headers.get("x-request-id")) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:  # anything the route did not handle
                logger.error("unhandled error", extra=exception_fields(exc))
                response = error_response(
                    500, "internal_error", "Something went wrong. Please try again."
                )
            response.headers["X-Request-ID"] = request_id
            route = request.scope.get("route")
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "route": route.path if route is not None else "unmatched",
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)


def _operation_id(route: APIRoute) -> str:
    # Readable method names in the generated TypeScript client (step 24).
    return route.name


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Hill Resort API",
        version="0.1.0",
        generate_unique_id_function=_operation_id,
    )
    if session_factory is None:
        session_factory = sessionmaker(
            bind=create_db_engine(settings.database_url), expire_on_commit=False
        )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.engine = session_factory.kw["bind"]

    # Added first, so it sits inside the request middleware (the last one added is outermost).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token", "Idempotency-Key"],
    )
    app.add_middleware(OriginCheckMiddleware, trusted_origins=settings.cors_origins)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    return app
