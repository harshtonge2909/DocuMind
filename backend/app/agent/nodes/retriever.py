# =============================================================================
# DocuMind — Agent Node: Retriever
# Performs hybrid search and formats context for the generator
# =============================================================================

import structlog
from typing import List, Dict, Any

from app.agent.state import AgentState
from app.services.search import hybrid_search, SearchHit
from app.config import settings

logger = structlog.get_logger(__name__)


def _format_chunks_as_context(hits: List[SearchHit]) -> str:
    """
    Format retrieved chunks into a structured context string for the LLM.
    Uses parent chunks when available for richer context.
    """
    context_parts = []
    for i, hit in enumerate(hits, 1):
        # Use parent content if available (broader context), else child content
        content = hit.parent_content or hit.content
        page_info = f"Page {hit.page_number}" if hit.page_number else "Unknown page"

        context_parts.append(
            f"[Source {i} | {page_info} | Score: {hit.score:.3f}]\n{content}"
        )

    return "\n\n---\n\n".join(context_parts)


def _chunks_to_citation_data(hits: List[SearchHit]) -> List[Dict[str, Any]]:
    """Convert search hits to citation metadata for the response."""
    citations = []
    for i, hit in enumerate(hits):
        citations.append({
            "source_index": i + 1,
            "chunk_id": str(hit.chunk_id),
            "page_number": hit.page_number,
            "page_numbers": hit.page_numbers,
            "text_snippet": hit.content[:300],  # First 300 chars for display
            "relevance_score": round(hit.score, 4),
            "search_type": hit.search_type,
            "has_parent": hit.parent_content is not None,
        })
    return citations


async def retrieve(state: AgentState, db_session) -> AgentState:
    """
    Retriever Node — Performs hybrid search for each sub-query.

    For complex queries: retrieves for each sub-query and merges results
    For simple queries: single retrieval pass

    Uses parent-child chunk strategy:
    - Matches on small child chunks (precise embeddings)
    - Returns parent chunks to the LLM (full context)
    """
    all_hits: List[SearchHit] = []
    all_citations: List[Dict[str, Any]] = []

    for sub_query in state.sub_queries:
        logger.info("Retrieving for sub-query", query=sub_query[:100])

        hits = await hybrid_search(
            query=sub_query,
            document_id=state.document_id,
            db=db_session,
            top_k=settings.top_k_results,
            search_type="hybrid",
        )

        all_hits.extend(hits)

    # Deduplicate by chunk_id (keep highest scoring)
    seen = {}
    for hit in all_hits:
        if hit.chunk_id not in seen or hit.score > seen[hit.chunk_id].score:
            seen[hit.chunk_id] = hit

    unique_hits = sorted(seen.values(), key=lambda h: h.score, reverse=True)
    top_hits = unique_hits[:settings.top_k_results]

    # Format context and citations
    state.retrieved_chunks = [
        {
            "chunk_id": str(h.chunk_id),
            "content": h.content,
            "parent_content": h.parent_content,
            "page_number": h.page_number,
            "score": h.score,
        }
        for h in top_hits
    ]
    state.retrieval_context = _format_chunks_as_context(top_hits)
    state.citations = _chunks_to_citation_data(top_hits)

    state.log_step(
        "retriever",
        f"Retrieved {len(top_hits)} chunks across {len(state.sub_queries)} sub-queries",
        chunk_count=len(top_hits),
        top_score=top_hits[0].score if top_hits else 0,
    )

    logger.info(
        "Retrieval complete",
        total_hits=len(top_hits),
        sub_queries=len(state.sub_queries),
    )

    return state
