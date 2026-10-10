# =============================================================================
# DocuMind — SQLAlchemy Model: Conversation
# Persistent chat threads tied to users and documents
# =============================================================================

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Conversation(Base):
    """A chat conversation thread between a user and a document."""

    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(500), nullable=False, default="New Chat")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="conversations")
    messages = relationship(
        "QueryHistory",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="QueryHistory.created_at",
    )

    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title[:40]}')>"
