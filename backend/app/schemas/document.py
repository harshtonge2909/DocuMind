# =============================================================================
# DocuMind — Pydantic Schemas: Document
# Request/Response schemas for document endpoints
# =============================================================================

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from enum import Enum


class DocumentStatusEnum(str, Enum):
    """Document processing status."""
    UPLOADING = "uploading"
    PROCESSING = "processing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"


class DocumentResponse(BaseModel):
    """Response schema for a document."""
    id: UUID
    filename: str
    original_name: str
    file_size: int
    file_hash: Optional[str] = None
    page_count: int = 0
    total_chunks: int = 0
    status: DocumentStatusEnum
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentListResponse(BaseModel):
    """Response schema for listing documents."""
    documents: List[DocumentResponse]
    total: int


class DocumentUploadResponse(BaseModel):
    """Response after successful document upload."""
    id: UUID
    original_name: str
    status: DocumentStatusEnum
    message: str


class DocumentDeleteResponse(BaseModel):
    """Response after document deletion."""
    id: UUID
    message: str
