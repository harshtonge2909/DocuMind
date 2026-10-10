# =============================================================================
# DocuMind — Pydantic Schemas: Usage & Billing
# =============================================================================

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class UsageResponse(BaseModel):
    """Current usage and tier information."""
    tier: str
    daily_used: int
    daily_limit: int
    remaining: int
    total_queries: int
    reset_date: str  # ISO date string

    model_config = {"from_attributes": True}


class TierUpdateRequest(BaseModel):
    """Request to change subscription tier."""
    tier: str = Field(..., pattern="^(free|pro)$", description="Target tier: 'free' or 'pro'")


class TierUpdateResponse(BaseModel):
    """Response after tier change."""
    user_id: str
    tier: str
    daily_limit: int
    message: str


class RateLimitError(BaseModel):
    """Error response when rate limit is exceeded."""
    detail: str = "Daily query limit reached"
    tier: str
    daily_used: int
    daily_limit: int
    upgrade_available: bool = True
