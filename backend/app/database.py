# =============================================================================
# DocuMind — Async Database Engine
# SQLAlchemy async setup with connection pooling for PostgreSQL + pgvector
# =============================================================================

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


# ─── Async Engine ────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,         # Verify connections before use
    pool_recycle=3600,           # Recycle connections after 1 hour
)

# ─── Session Factory ─────────────────────────────────────────────────────────
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ─── Base Model ──────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# ─── Dependency ──────────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── Health Check ────────────────────────────────────────────────────────────
async def check_db_health() -> dict:
    """Check database connectivity and pgvector extension."""
    try:
        async with async_session() as session:
            # Basic connectivity
            result = await session.execute(text("SELECT 1"))
            result.scalar()

            # Check pgvector extension
            result = await session.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            pgvector_version = result.scalar()

            return {
                "status": "healthy",
                "pgvector_version": pgvector_version or "not installed",
            }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}
