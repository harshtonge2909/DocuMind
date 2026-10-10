# =============================================================================
# DocuMind — Pydantic Schemas: Query
# Request/Response schemas for query endpoints
# =============================================================================

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID


class Citation(BaseModel):
    """A citation linking answer text to a source chunk."""
    chunk_id: UUID
    page_number: Optional[int] = None
    page_numbers: Optional[List[int]] = None
    text_snippet: str
    relevance_score: float = 0.0
    bbox: Optional[Dict[str, Any]] = None


class QueryRequest(BaseModel):
    """Request schema for asking a question."""
    query: str = Field(..., min_length=1, max_length=2000, description="The question to ask")
    document_id: UUID = Field(..., description="ID of the document to query against")
    conversation_id: Optional[UUID] = Field(None, description="Conversation thread ID; auto-created if omitted")
    stream: bool = Field(default=True, description="Whether to stream the response via SSE")



class QueryResponse(BaseModel):
    """Complete response to a query."""
    query_id: UUID
    query: str
    answer: str
    citations: List[Citation] = []
    sub_queries: List[str] = []
    agent_steps: List[Dict[str, Any]] = []
    latency_ms: int
    cached: bool = False
    confidence_score: Optional[float] = None


class SearchRequest(BaseModel):
    """Request schema for direct search (without LLM generation)."""
    query: str = Field(..., min_length=1, max_length=2000)
    document_id: UUID
    top_k: int = Field(default=10, ge=1, le=50)
    search_type: str = Field(default="hybrid", pattern="^(semantic|keyword|hybrid)$")


class SearchResult(BaseModel):
    """A single search result."""
    chunk_id: UUID
    content: str
    page_number: Optional[int] = None
    score: float
    search_type: str
    metadata: Dict[str, Any] = {}


class SearchResponse(BaseModel):
    """Response containing search results."""
    results: List[SearchResult]
    total: int
    search_type: str
    latency_ms: int
