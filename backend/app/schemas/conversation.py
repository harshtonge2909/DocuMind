# =============================================================================
# DocuMind — Pydantic Schemas: Conversation
# Request/Response schemas for chat history & threads
# =============================================================================

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID


class ConversationCreate(BaseModel):
    """Request to create a new conversation."""
    document_id: UUID = Field(..., description="ID of the document this conversation is about")
    title: Optional[str] = Field(None, max_length=500, description="Optional title; auto-generated from first query if omitted")


class MessageResponse(BaseModel):
    """A single message (query + answer) within a conversation."""
    id: UUID
    role: str  # "user" or "assistant"
    content: str
    citations: List[Dict[str, Any]] = []
    sub_queries: List[str] = []
    confidence_score: Optional[float] = None
    latency_ms: Optional[int] = None
    cached: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    """A conversation thread summary."""
    id: UUID
    document_id: UUID
    title: str
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(BaseModel):
    """A conversation with its full message history."""
    id: UUID
    document_id: UUID
    title: str
    messages: List[MessageResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""
    conversations: List[ConversationResponse]
    total: int


class ConversationUpdateRequest(BaseModel):
    """Request to update a conversation (e.g., rename)."""
    title: str = Field(..., min_length=1, max_length=500)
