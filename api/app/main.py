from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import init_db, close_db


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


from app.routers import documents, analysis, webhooks, auth  # noqa: E402

app.include_router(auth.router, prefix=settings.API_PREFIX, tags=["auth"])
app.include_router(documents.router, prefix=settings.API_PREFIX, tags=["documents"])
app.include_router(analysis.router, prefix=settings.API_PREFIX, tags=["analysis"])
app.include_router(webhooks.router, prefix=settings.API_PREFIX, tags=["webhooks"])