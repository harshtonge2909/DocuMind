# =============================================================================
# DocuMind — Redis Client Provider
# Shared module to avoid circular imports between main.py and API routes
# =============================================================================

import redis.asyncio as aioredis
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# Module-level Redis client (initialized by main.py lifespan)
_redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis | None:
    """Initialize the Redis connection. Called from main.py lifespan."""
    global _redis_client
    try:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        await _redis_client.ping()
        logger.info("✅ Redis connected", host=settings.redis_host)
        return _redis_client
    except Exception as e:
        logger.warning("⚠️  Redis connection failed (caching disabled)", error=str(e))
        _redis_client = None
        return None


async def close_redis() -> None:
    """Close the Redis connection. Called from main.py lifespan."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        logger.info("Redis connection closed")
        _redis_client = None


def get_redis_client() -> aioredis.Redis | None:
    """Get the global Redis client instance (for dependency injection)."""
    return _redis_client
