# =============================================================================
# DocuMind — Rate Limiting Service
# Redis-backed per-user rate limiting with tier-based quotas
# =============================================================================

import structlog
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import UserTier
from app.config import settings

logger = structlog.get_logger(__name__)

# Tier-based daily query limits
TIER_LIMITS = {
    "free": 10,
    "pro": 999999,  # Effectively unlimited
}


class RateLimitResult:
    """Result of a rate limit check."""

    def __init__(
        self,
        allowed: bool,
        tier: str,
        daily_used: int,
        daily_limit: int,
        total_queries: int,
    ):
        self.allowed = allowed
        self.tier = tier
        self.daily_used = daily_used
        self.daily_limit = daily_limit
        self.remaining = max(0, daily_limit - daily_used)
        self.total_queries = total_queries

    @property
    def headers(self) -> dict[str, str]:
        """Rate limit headers to include in API responses."""
        return {
            "X-RateLimit-Limit": str(self.daily_limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Used": str(self.daily_used),
            "X-User-Tier": self.tier,
        }


async def get_or_create_user_tier(user_id: str, db: AsyncSession) -> UserTier:
    """Get or create a UserTier record for the given user."""
    result = await db.execute(
        select(UserTier).where(UserTier.user_id == user_id)
    )
    user_tier = result.scalar_one_or_none()

    if not user_tier:
        user_tier = UserTier(
            user_id=user_id,
            tier="free",
            daily_query_count=0,
            last_reset_date=date.today(),
            total_queries=0,
        )
        db.add(user_tier)
        await db.flush()
        await db.refresh(user_tier)
        logger.info("Created user tier", user_id=user_id, tier="free")

    return user_tier


async def check_rate_limit(user_id: str, db: AsyncSession) -> RateLimitResult:
    """
    Check if the user is within their rate limit.

    Resets daily count if the date has changed.
    Returns a RateLimitResult with allowed/denied status and headers.
    """
    user_tier = await get_or_create_user_tier(user_id, db)

    # Reset daily count if it's a new day
    today = date.today()
    if user_tier.last_reset_date != today:
        user_tier.daily_query_count = 0
        user_tier.last_reset_date = today
        await db.flush()
        logger.info("Daily query count reset", user_id=user_id)

    daily_limit = TIER_LIMITS.get(user_tier.tier, TIER_LIMITS["free"])
    allowed = user_tier.daily_query_count < daily_limit

    return RateLimitResult(
        allowed=allowed,
        tier=user_tier.tier,
        daily_used=user_tier.daily_query_count,
        daily_limit=daily_limit,
        total_queries=user_tier.total_queries,
    )


async def increment_usage(user_id: str, db: AsyncSession) -> None:
    """Increment the user's daily and total query counts after a successful query."""
    user_tier = await get_or_create_user_tier(user_id, db)
    user_tier.daily_query_count += 1
    user_tier.total_queries += 1
    await db.flush()

    logger.info(
        "Usage incremented",
        user_id=user_id,
        daily=user_tier.daily_query_count,
        total=user_tier.total_queries,
    )


async def set_user_tier(user_id: str, tier: str, db: AsyncSession) -> UserTier:
    """Set a user's subscription tier (admin/mock billing action)."""
    if tier not in TIER_LIMITS:
        raise ValueError(f"Invalid tier: {tier}. Must be one of {list(TIER_LIMITS.keys())}")

    user_tier = await get_or_create_user_tier(user_id, db)
    user_tier.tier = tier
    await db.flush()
    await db.refresh(user_tier)

    logger.info("User tier updated", user_id=user_id, tier=tier)
    return user_tier
