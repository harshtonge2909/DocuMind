# =============================================================================
# DocuMind — API Routes: Search
# Direct search endpoint for testing hybrid search independently
# =============================================================================

import time
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, DocumentStatus
from app.schemas import SearchRequest, SearchResult, SearchResponse
from app.services.search import hybrid_search

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Search through document chunks using hybrid search.

    Supports three modes:
    - **hybrid**: Semantic + BM25 with Reciprocal Rank Fusion (default)
    - **semantic**: Vector similarity only
    - **keyword**: BM25 keyword matching only
    """
    start_time = time.time()

    # Verify document exists and is ready
    from sqlalchemy import select
    result = await db.execute(
        select(Document).where(Document.id == request.document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Document is not ready for search. Current status: {document.status}"
        )

    # Perform search
    hits = await hybrid_search(
        query=request.query,
        document_id=request.document_id,
        db=db,
        top_k=request.top_k,
        search_type=request.search_type,
    )

    latency_ms = int((time.time() - start_time) * 1000)

    # Convert to response schema
    results = [
        SearchResult(
            chunk_id=hit.chunk_id,
            content=hit.parent_content or hit.content,  # Return parent content if available
            page_number=hit.page_number,
            score=round(hit.score, 4),
            search_type=hit.search_type,
            metadata={
                "child_content": hit.content[:200] + "..." if hit.parent_content else None,
                "page_numbers": hit.page_numbers,
                **(hit.metadata or {}),
            },
        )
        for hit in hits
    ]

    return SearchResponse(
        results=results,
        total=len(results),
        search_type=request.search_type,
        latency_ms=latency_ms,
    )
