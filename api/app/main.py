import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, settings
from app.tier_config import feature_enabled, register_tier_routes
from app.db.session import init_db, close_db

logger = logging.getLogger(__name__)


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return {"status": "ready", "service": "api"}


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

# Feature-gated routers
if feature_enabled("rules_engine"):
    from app.routers import rules  # noqa: E402
    app.include_router(rules.router, prefix=settings.API_PREFIX, tags=["rules"])

if feature_enabled("nl_query"):
    from app.routers import nl_query  # noqa: E402
    app.include_router(nl_query.router, prefix=settings.API_PREFIX, tags=["nl-query"])

if feature_enabled("fraud_detection"):
    from app.routers import fraud  # noqa: E402
    app.include_router(fraud.router, prefix=settings.API_PREFIX, tags=["fraud"])

if feature_enabled("three_way_match"):
    from app.routers import three_way_match  # noqa: E402
    app.include_router(three_way_match.router, prefix=settings.API_PREFIX, tags=["three-way-match"])

if feature_enabled("approval_routing"):
    from app.routers import approval_routing  # noqa: E402
    app.include_router(approval_routing.router, prefix=settings.API_PREFIX, tags=["approval-routing"])

if feature_enabled("reporting"):
    from app.routers import reporting  # noqa: E402
    app.include_router(reporting.router, prefix=settings.API_PREFIX, tags=["reporting"])

# Tier info endpoint (always available)
from app.tier_config.tiers import register_tier_routes
register_tier_routes(app)