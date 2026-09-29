import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.logging_config import configure_logging
from app.tier_config import register_tier_routes
from app.db.session import init_db, close_db

configure_logging()

logger = logging.getLogger(__name__)


class ExceptionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to catch all unhandled exceptions and return a clean 500 response.
    This acts as a final safety net beyond @app.exception_handler.
    """
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception(f"Unhandled exception caught by middleware: {exc}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Final safety net middleware.
# NOTE: this must be added BEFORE CORSMiddleware. Starlette executes the
# most-recently-added middleware outermost, so adding CORS last keeps it
# outermost and guarantees CORS headers are attached even to 500 responses
# produced by this handler. Otherwise browsers report a CORS error instead
# of the real status code.
app.add_middleware(ExceptionMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request_id to every structured log line for this request."""

    async def dispatch(self, request: Request, call_next):
        from app.logging_config import bind_context, clear_context, new_request_id

        request_id = request.headers.get("X-Request-ID") or new_request_id()
        bind_context(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_context()
        response.headers["X-Request-ID"] = request_id
        return response


# Added last so it runs outermost: the ID is bound before anything else
# logs, including the exception safety net below CORS.
app.add_middleware(RequestContextMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler - never expose stack traces to clients."""
    logger.exception(f"Unhandled exception on {request.method} {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "api", "version": settings.APP_VERSION}


@app.get("/health/ready", tags=["health"])
async def readiness_check():
    """Ready only if DB and Redis are both reachable, else 503."""
    checks = {}
    try:
        from sqlalchemy import text
        from app.db.session import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        logger.exception(f"Readiness DB check failed: {exc}")
        checks["db"] = "error"
    try:
        import redis.asyncio as redis
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        await client.ping()
        await client.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.exception(f"Readiness Redis check failed: {exc}")
        checks["redis"] = "error"
    if all(v == "ok" for v in checks.values()):
        return {"status": "ready", "service": "api", "checks": checks}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "service": "api", "checks": checks},
    )


@app.get("/health/live", tags=["health"])
async def liveness_check():
    return {"status": "alive", "service": "api"}


@app.get(settings.API_PREFIX + "/health", tags=["health"], include_in_schema=False)
async def api_health_check():
    return {"status": "ok", "service": "api", "version": settings.APP_VERSION}


# Core routers (always enabled)
from app.routers import auth, documents  # noqa: E402

app.include_router(auth.router, prefix=settings.API_PREFIX, tags=["auth"])
app.include_router(documents.router, prefix=settings.API_PREFIX, tags=["documents"])

# Feature-gated routers (now included and gated via dependencies in the routers themselves)
from app.routers import rules, nl_query, fraud, three_way_match, approval_routing, reporting, purchase_orders  # noqa: E402

app.include_router(rules.router, prefix=settings.API_PREFIX, tags=["rules"])
app.include_router(nl_query.router, prefix=settings.API_PREFIX, tags=["nl-query"])
app.include_router(fraud.router, prefix=settings.API_PREFIX, tags=["fraud"])
app.include_router(three_way_match.router, prefix=settings.API_PREFIX, tags=["three-way-match"])
app.include_router(approval_routing.router, prefix=settings.API_PREFIX, tags=["approval-routing"])
app.include_router(reporting.router, prefix=settings.API_PREFIX, tags=["reporting"])
app.include_router(purchase_orders.router, prefix=settings.API_PREFIX, tags=["purchase-orders"])

# Tier info endpoint (always available)
register_tier_routes(app)
