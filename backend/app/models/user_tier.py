# =============================================================================
# DocuMind — SQLAlchemy Model: UserTier
# Tracks subscription tiers and daily usage for rate limiting
# =============================================================================

import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, Integer, Date, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database import Base


class TierLevel(str, enum.Enum):
    FREE = "free"
    PRO = "pro"


class UserTier(Base):
    """Tracks a user's subscription tier and daily query usage."""

    __tablename__ = "user_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, unique=True, index=True)
    tier = Column(
        SAEnum("free", "pro", name="tier_level", create_type=False),
        nullable=False,
        default="free",
    )
    daily_query_count = Column(Integer, nullable=False, default=0)
    last_reset_date = Column(Date, nullable=False, default=date.today)
    total_queries = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<UserTier(user_id='{self.user_id}', tier='{self.tier}', daily={self.daily_query_count})>"
