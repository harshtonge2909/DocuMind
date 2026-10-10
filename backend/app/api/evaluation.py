# =============================================================================
# DocuMind — API Routes: Evaluation
# Dashboard metrics and query evaluation endpoints
# =============================================================================

import uuid
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.evaluation import get_evaluation_metrics
from app.services.cache import SemanticCache
from app.redis_client import get_redis_client

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/eval", tags=["Evaluation"])


@router.get("/metrics")
async def get_metrics(
    document_id: Optional[uuid.UUID] = Query(None, description="Filter by document ID"),
    limit: int = Query(100, ge=1, le=500, description="Max evaluations to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get evaluation metrics for the dashboard.

    Returns:
    - Summary: aggregated averages across all queries
    - Evaluations: individual query evaluation records
    - Timeline: time-series data for charts

    Optionally filter by document_id.
    """
    metrics = await get_evaluation_metrics(db, document_id, limit)
    return metrics


@router.get("/cache-stats")
async def get_cache_stats():
    """Get semantic cache performance statistics."""
    redis_client = get_redis_client()
    if not redis_client:
        return {
            "status": "disabled",
            "message": "Redis is not connected. Semantic caching is disabled.",
        }

    cache = SemanticCache(redis_client)
    stats = await cache.get_stats()
    return stats
