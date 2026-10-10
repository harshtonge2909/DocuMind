# =============================================================================
# DocuMind — SQLAlchemy Models: Chunk
# =============================================================================

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Enum as SAEnum,
    ForeignKey, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import enum

from app.database import Base
from app.config import settings


class ChunkType(str, enum.Enum):
    """Chunk hierarchy type."""
    PARENT = "parent"
    CHILD = "child"


class Chunk(Base):
    """Represents a text chunk from a document with its embedding."""

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    page_numbers = Column(ARRAY(Integer), nullable=True)
    chunk_kind = Column(
        SAEnum(
            "parent", "child",
            name="chunk_type",
            create_type=False,
        ),
        default="child"
    )
    parent_chunk_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="SET NULL"),
        nullable=True
    )
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    bbox = Column(JSONB, nullable=True)
    embedding = Column(Vector(settings.embedding_dimensions))
    token_count = Column(Integer, default=0)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="chunks")
    parent_chunk = relationship("Chunk", remote_side=[id], backref="children")

    def __repr__(self):
        return (
            f"<Chunk(id={self.id}, doc={self.document_id}, "
            f"index={self.chunk_index}, type={self.chunk_kind})>"
        )
