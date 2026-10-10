# =============================================================================
# DocuMind — SQLAlchemy Models: Document
# =============================================================================

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Enum as SAEnum, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class DocumentStatus(str, enum.Enum):
    """Document processing status."""
    UPLOADING = "uploading"
    PROCESSING = "processing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"


class Document(Base):
    """Represents an uploaded PDF document."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    filename = Column(String(500), nullable=False)
    original_name = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=True)
    page_count = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    status = Column(
        SAEnum(
            "uploading", "processing", "chunking", "embedding", "ready", "error",
            name="document_status",
            create_type=False,
        ),
        default="uploading"
    )
    error_message = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    queries = relationship("QueryHistory", back_populates="document")
    conversations = relationship("Conversation", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(id={self.id}, name='{self.original_name}', status={self.status})>"
