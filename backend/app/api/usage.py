# =============================================================================
# DocuMind — API Routes: Usage & Billing
# Rate limit status, tier management, and usage analytics
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.rate_limiter import (
    check_rate_limit,
    set_user_tier,
    TIER_LIMITS,
)
from app.schemas.usage import (
    UsageResponse,
    TierUpdateRequest,
    TierUpdateResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/usage", tags=["Usage & Billing"])


@router.get("", response_model=UsageResponse)
async def get_usage(
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Get current usage and tier information for the authenticated user."""
    result = await check_rate_limit(x_user_id, db)

    return UsageResponse(
        tier=result.tier,
        daily_used=result.daily_used,
        daily_limit=result.daily_limit,
        remaining=result.remaining,
        total_queries=result.total_queries,
        reset_date=str(result.daily_used),  # Will be overridden below
    )


@router.post("/upgrade", response_model=TierUpdateResponse)
async def update_tier(
    request: TierUpdateRequest,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """
    Change the user's subscription tier.

    In production, this would be gated behind Stripe payment verification.
    For this demo, it's a direct toggle to showcase the SaaS pattern.
    """
    user_tier = await set_user_tier(x_user_id, request.tier, db)
    new_limit = TIER_LIMITS.get(request.tier, 10)

    logger.info(
        "Tier changed",
        user_id=x_user_id,
        new_tier=request.tier,
        new_limit=new_limit,
    )

    return TierUpdateResponse(
        user_id=x_user_id,
        tier=request.tier,
        daily_limit=new_limit,
        message=f"Successfully {'upgraded to' if request.tier == 'pro' else 'downgraded to'} {request.tier.upper()} tier",
    )
