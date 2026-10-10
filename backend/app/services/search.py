# =============================================================================
# DocuMind — Hybrid Search Service
# Pgvector (semantic) + BM25 (keyword) with Reciprocal Rank Fusion (RRF)
# =============================================================================

import uuid
import numpy as np
import structlog
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from rank_bm25 import BM25Okapi

from app.config import settings
from app.models import Chunk
from app.services.embeddings import generate_single_embedding

logger = structlog.get_logger(__name__)


@dataclass
class SearchHit:
    """A single search result with metadata."""
    chunk_id: uuid.UUID
    content: str
    page_number: Optional[int]
    page_numbers: List[int]
    score: float
    search_type: str       # "semantic", "keyword", or "hybrid"
    parent_content: Optional[str] = None
    parent_chunk_id: Optional[uuid.UUID] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# =============================================================================
# Semantic Search (Pgvector)
# =============================================================================

async def semantic_search(
    query_embedding: List[float],
    document_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 10,
    similarity_threshold: float = 0.0,
) -> List[SearchHit]:
    """
    Vector similarity search using pgvector's cosine distance.

    Searches only child chunks (which have embeddings) and optionally
    fetches the parent chunk for expanded context.
    """
    # Use pgvector's <=> operator for cosine distance
    # Note: pgvector uses distance (lower = more similar), so we convert to similarity
    query = text("""
        SELECT
            c.id,
            c.content,
            c.page_number,
            c.page_numbers,
            c.parent_chunk_id,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity,
            p.content AS parent_content
        FROM chunks c
        LEFT JOIN chunks p ON c.parent_chunk_id = p.id
        WHERE c.document_id = :doc_id
          AND c.chunk_kind = 'child'
          AND c.embedding IS NOT NULL
          AND 1 - (c.embedding <=> CAST(:embedding AS vector)) >= :threshold
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)

    result = await db.execute(
        query,
        {
            "embedding": str(query_embedding),
            "doc_id": str(document_id),
            "threshold": similarity_threshold,
            "top_k": top_k,
        },
    )

    hits = []
    for row in result.fetchall():
        hits.append(SearchHit(
            chunk_id=row.id,
            content=row.content,
            page_number=row.page_number,
            page_numbers=row.page_numbers or [],
            score=float(row.similarity),
            search_type="semantic",
            parent_content=row.parent_content,
            parent_chunk_id=row.parent_chunk_id,
        ))

    logger.info("Semantic search", results=len(hits), top_score=hits[0].score if hits else 0)
    return hits


# =============================================================================
# BM25 Keyword Search
# =============================================================================

async def keyword_search(
    query: str,
    document_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 10,
) -> List[SearchHit]:
    """
    BM25 keyword search using PostgreSQL full-text search.

    Uses ts_vector and ts_rank for efficient keyword matching.
    Falls back to in-memory BM25 for more accurate ranking.
    """
    # Step 1: Use PostgreSQL full-text search to get candidate chunks
    fts_query = text("""
        SELECT
            c.id,
            c.content,
            c.page_number,
            c.page_numbers,
            c.parent_chunk_id,
            p.content AS parent_content,
            ts_rank_cd(to_tsvector('english', c.content), plainto_tsquery('english', :query)) AS pg_rank
        FROM chunks c
        LEFT JOIN chunks p ON c.parent_chunk_id = p.id
        WHERE c.document_id = :doc_id
          AND c.chunk_kind = 'child'
          AND to_tsvector('english', c.content) @@ plainto_tsquery('english', :query)
        ORDER BY pg_rank DESC
        LIMIT :candidate_limit
    """)

    result = await db.execute(
        fts_query,
        {
            "query": query,
            "doc_id": str(document_id),
            "candidate_limit": top_k * 3,  # Get more candidates for BM25 re-ranking
        },
    )

    candidates = result.fetchall()

    if not candidates:
        # Fallback: if FTS returns nothing, try loading all child chunks for BM25
        logger.info("FTS returned no results, falling back to in-memory BM25")
        all_chunks_result = await db.execute(
            select(Chunk)
            .where(
                Chunk.document_id == document_id,
                Chunk.chunk_kind == "child",
            )
            .limit(1000)
        )
        all_chunks = all_chunks_result.scalars().all()

        if not all_chunks:
            return []

        # In-memory BM25 ranking
        tokenized_corpus = [c.content.lower().split() for c in all_chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query.lower().split())

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]

        hits = []
        for idx in top_indices:
            if scores[idx] > 0:
                chunk = all_chunks[idx]
                hits.append(SearchHit(
                    chunk_id=chunk.id,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    page_numbers=chunk.page_numbers or [],
                    score=float(scores[idx]),
                    search_type="keyword",
                    parent_chunk_id=chunk.parent_chunk_id,
                ))

        return hits

    # Step 2: Re-rank with BM25 for better accuracy
    tokenized_corpus = [row.content.lower().split() for row in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(query.lower().split())

    # Combine results with BM25 scores
    scored_candidates = list(zip(candidates, scores))
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    hits = []
    for row, score in scored_candidates[:top_k]:
        if score > 0:
            hits.append(SearchHit(
                chunk_id=row.id,
                content=row.content,
                page_number=row.page_number,
                page_numbers=row.page_numbers or [],
                score=float(score),
                search_type="keyword",
                parent_content=row.parent_content,
                parent_chunk_id=row.parent_chunk_id,
            ))

    logger.info("Keyword search", results=len(hits), top_score=hits[0].score if hits else 0)
    return hits


# =============================================================================
# Reciprocal Rank Fusion (RRF)
# =============================================================================

def reciprocal_rank_fusion(
    semantic_hits: List[SearchHit],
    keyword_hits: List[SearchHit],
    semantic_weight: float = 0.6,
    keyword_weight: float = 0.4,
    k: int = 60,  # RRF constant
    top_k: int = 10,
) -> List[SearchHit]:
    """
    Merge semantic and keyword search results using Reciprocal Rank Fusion.

    RRF Score = Σ (weight / (k + rank))

    This gives a balanced ranking that leverages both semantic understanding
    and exact keyword matching.

    Args:
        semantic_hits: Results from vector similarity search
        keyword_hits: Results from BM25 keyword search
        semantic_weight: Weight for semantic results (default 0.6)
        keyword_weight: Weight for keyword results (default 0.4)
        k: RRF constant (default 60, standard value from the paper)
        top_k: Number of results to return

    Returns:
        Fused list of SearchHit objects with combined scores
    """
    # Build RRF scores per chunk
    rrf_scores: Dict[uuid.UUID, float] = {}
    chunk_data: Dict[uuid.UUID, SearchHit] = {}

    # Score semantic hits
    for rank, hit in enumerate(semantic_hits):
        rrf_score = semantic_weight / (k + rank + 1)
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0) + rrf_score
        chunk_data[hit.chunk_id] = hit

    # Score keyword hits
    for rank, hit in enumerate(keyword_hits):
        rrf_score = keyword_weight / (k + rank + 1)
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0) + rrf_score
        if hit.chunk_id not in chunk_data:
            chunk_data[hit.chunk_id] = hit

    # Sort by RRF score
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    # Build final results
    fused_hits = []
    for chunk_id in sorted_ids[:top_k]:
        hit = chunk_data[chunk_id]
        fused_hit = SearchHit(
            chunk_id=hit.chunk_id,
            content=hit.content,
            page_number=hit.page_number,
            page_numbers=hit.page_numbers,
            score=rrf_scores[chunk_id],
            search_type="hybrid",
            parent_content=hit.parent_content,
            parent_chunk_id=hit.parent_chunk_id,
            metadata={
                "rrf_score": rrf_scores[chunk_id],
                "in_semantic": chunk_id in {h.chunk_id for h in semantic_hits},
                "in_keyword": chunk_id in {h.chunk_id for h in keyword_hits},
            },
        )
        fused_hits.append(fused_hit)

    logger.info(
        "RRF fusion",
        semantic_count=len(semantic_hits),
        keyword_count=len(keyword_hits),
        fused_count=len(fused_hits),
    )

    return fused_hits


# =============================================================================
# Main Hybrid Search Entry Point
# =============================================================================

async def hybrid_search(
    query: str,
    document_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = None,
    search_type: str = "hybrid",
) -> List[SearchHit]:
    """
    Perform hybrid search combining semantic and keyword search with RRF.

    This is the main search entry point used by the LangGraph agent.

    Args:
        query: Search query string
        document_id: UUID of the document to search
        db: Async database session
        top_k: Number of results to return
        search_type: "hybrid", "semantic", or "keyword"

    Returns:
        List of SearchHit objects ranked by relevance
    """
    if top_k is None:
        top_k = settings.top_k_results

    # Generate query embedding for semantic search
    query_embedding = await generate_single_embedding(query)

    if search_type == "semantic":
        return await semantic_search(
            query_embedding, document_id, db, top_k,
            settings.similarity_threshold
        )

    if search_type == "keyword":
        return await keyword_search(query, document_id, db, top_k)

    # Hybrid: run both searches
    semantic_hits = await semantic_search(
        query_embedding, document_id, db, top_k * 2,
        similarity_threshold=0.0,  # Don't filter for RRF
    )

    keyword_hits = await keyword_search(
        query, document_id, db, top_k * 2
    )

    # Fuse results using RRF
    fused = reciprocal_rank_fusion(
        semantic_hits=semantic_hits,
        keyword_hits=keyword_hits,
        semantic_weight=settings.semantic_search_weight,
        keyword_weight=settings.bm25_search_weight,
        top_k=top_k,
    )

    return fused
