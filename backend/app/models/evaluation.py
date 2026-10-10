# =============================================================================
# DocuMind — SQLAlchemy Models: Evaluation & Query History
# =============================================================================

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, Boolean, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.database import Base
from app.config import settings


class QueryHistory(Base):
    """Tracks all queries and their responses for evaluation."""

    __tablename__ = "query_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    query_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=True)
    citations = Column(JSONB, default=list)
    agent_steps = Column(JSONB, default=list)
    sub_queries = Column(JSONB, default=list)
    latency_ms = Column(Integer, nullable=True)
    token_usage = Column(JSONB, default=dict)
    cached = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="queries")
    conversation = relationship("Conversation", back_populates="messages")
    evaluation = relationship(
        "Evaluation", back_populates="query", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<QueryHistory(id={self.id}, query='{self.query_text[:50]}...')>"


class Evaluation(Base):
    """Ragas evaluation metrics for a query-answer pair."""

    __tablename__ = "evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(
        UUID(as_uuid=True),
        ForeignKey("query_history.id", ondelete="CASCADE"),
        nullable=False
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    faithfulness = Column(Float, nullable=True)
    answer_relevancy = Column(Float, nullable=True)
    context_precision = Column(Float, nullable=True)
    context_recall = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    eval_metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    query = relationship("QueryHistory", back_populates="evaluation")

    def __repr__(self):
        return (
            f"<Evaluation(id={self.id}, faithfulness={self.faithfulness}, "
            f"relevancy={self.answer_relevancy})>"
        )


class CacheEntry(Base):
    """Tracks semantic cache entries for analytics."""

    __tablename__ = "cache_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_hash = Column(String(64), nullable=False)
    query_text = Column(Text, nullable=False)
    query_embedding = Column(Vector(settings.embedding_dimensions), nullable=True)
    response_text = Column(Text, nullable=False)
    citations = Column(JSONB, default=list)
    hit_count = Column(Integer, default=0)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<CacheEntry(id={self.id}, hits={self.hit_count})>"
