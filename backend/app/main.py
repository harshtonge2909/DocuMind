# =============================================================================
# DocuMind — FastAPI Application Entry Point
# Agentic RAG Research Assistant
# =============================================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.config import settings
from app.api import api_router
from app.database import check_db_health
from app.redis_client import init_redis, close_redis, get_redis_client

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Runs on startup and shutdown.
    """
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info(
        "🧠 DocuMind starting up",
        version=settings.app_version,
        debug=settings.debug,
    )

    # Initialize Redis connection
    await init_redis()

    # Check database health
    db_health = await check_db_health()
    if db_health["status"] == "healthy":
        logger.info(
            "✅ PostgreSQL connected",
            pgvector=db_health.get("pgvector_version"),
        )
    else:
        logger.error("❌ PostgreSQL health check failed", **db_health)

    yield  # Application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("🧠 DocuMind shutting down")
    await close_redis()


# ─── Create FastAPI App ──────────────────────────────────────────────────────
app = FastAPI(
    title="DocuMind",
    description=(
        "🧠 Agentic RAG Research Assistant — "
        "Upload PDFs, ask complex multi-hop questions, "
        "get cited and verified answers with source highlights."
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS Middleware ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Include API Routes ─────────────────────────────────────────────────────
app.include_router(api_router)


# ─── Root & Health Endpoints ─────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint — API info."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "description": "Agentic RAG Research Assistant",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Comprehensive health check for all services.
    Returns status of PostgreSQL, Redis, and pgvector.
    """
    redis_client = get_redis_client()

    # Database health
    db_health = await check_db_health()

    # Redis health
    redis_health = {"status": "disabled"}
    if redis_client:
        try:
            await redis_client.ping()
            redis_info = await redis_client.info("memory")
            redis_health = {
                "status": "healthy",
                "used_memory": redis_info.get("used_memory_human", "unknown"),
            }
        except Exception as e:
            redis_health = {"status": "unhealthy", "error": str(e)}

    # Overall status
    overall = "healthy" if db_health["status"] == "healthy" else "degraded"

    return JSONResponse(
        status_code=200 if overall == "healthy" else 503,
        content={
            "status": overall,
            "version": settings.app_version,
            "services": {
                "database": db_health,
                "redis": redis_health,
            },
        },
    )
