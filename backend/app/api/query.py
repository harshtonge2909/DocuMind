# =============================================================================
# DocuMind — API Routes: Query
# Ask questions about documents with SSE streaming
# =============================================================================

import json
import uuid
import asyncio
import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Document, DocumentStatus, Conversation
from app.schemas import QueryRequest, QueryResponse
from app.agent.graph import run_agent_pipeline, stream_agent_pipeline, run_eval_bg
from app.services.rate_limiter import check_rate_limit, increment_usage

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/query", tags=["Query"])


async def _validate_document(document_id: uuid.UUID, db: AsyncSession, user_id: str) -> Document:
    """Validate document exists and is ready for querying."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.status != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Document is not ready for querying. Status: {document.status}"
        )

    return document


async def _resolve_conversation(
    conversation_id: uuid.UUID | None,
    document_id: uuid.UUID,
    query: str,
    user_id: str,
    db: AsyncSession,
) -> uuid.UUID:
    """Resolve or auto-create a conversation for this query."""
    if conversation_id:
        # Validate it exists and belongs to user
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv.id

    # Auto-create a new conversation titled from the first query
    title = query[:80] + ("..." if len(query) > 80 else "")
    conversation = Conversation(
        user_id=user_id,
        document_id=document_id,
        title=title,
    )
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    logger.info("Auto-created conversation", conversation_id=str(conversation.id))
    return conversation.id


@router.post("", response_model=QueryResponse)
async def ask_question(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """
    Ask a question about a document.

    The agentic RAG pipeline will:
    1. Analyze query complexity and decompose if needed
    2. Perform hybrid search (semantic + BM25 + RRF)
    3. Generate a cited answer
    4. Self-evaluate and re-retrieve if confidence is low

    Use `stream: true` for SSE streaming (recommended for UI).
    """
    await _validate_document(request.document_id, db, x_user_id)

    # ── Rate Limit Check ─────────────────────────────────────────────────
    rate_result = await check_rate_limit(x_user_id, db)
    if not rate_result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "message": f"Daily query limit reached ({rate_result.daily_limit} queries/day on {rate_result.tier.upper()} tier). Upgrade to Pro for unlimited queries.",
                "tier": rate_result.tier,
                "daily_used": rate_result.daily_used,
                "daily_limit": rate_result.daily_limit,
                "upgrade_available": rate_result.tier == "free",
            },
            headers=rate_result.headers,
        )

    # Increment usage count
    await increment_usage(x_user_id, db)

    # Resolve or create conversation
    conversation_id = await _resolve_conversation(
        request.conversation_id, request.document_id, request.query, x_user_id, db
    )

    if request.stream:
        # Return SSE streaming response
        async def event_generator():
            try:
                final_query_id = uuid.uuid4()
                final_answer = ""
                final_citations = []
                
                async for event in stream_agent_pipeline(
                    query=request.query,
                    document_id=request.document_id,
                    db=db,
                    user_id=x_user_id,
                    conversation_id=conversation_id,
                ):
                    # Inject conversation_id into the complete event
                    if event["event"] == "complete":
                        event["data"]["conversation_id"] = str(conversation_id)
                        final_query_id = uuid.UUID(event["data"]["query_id"])
                        final_answer = event["data"]["answer"]
                        final_citations = event["data"].get("citations", [])
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                    
                # Fire evaluation in the background using FastAPI BackgroundTasks
                # This ensures the task is tracked and not garbage collected mid-execution
                contexts = [c.get("text_snippet", "") for c in final_citations]
                logger.info(
                    "DEBUG eval pre-check",
                    final_citations_count=len(final_citations),
                    final_citations_keys=[list(c.keys()) for c in final_citations[:2]] if final_citations else [],
                    contexts_preview=[ctx[:80] for ctx in contexts[:3]],
                    contexts_empty=all(not c.strip() for c in contexts) if contexts else True,
                    has_answer=bool(final_answer),
                    answer_len=len(final_answer),
                    query_id=str(final_query_id),
                )
                if final_answer and final_query_id:
                    logger.info(
                        "Scheduling stream eval",
                        query_id=str(final_query_id),
                        context_count=len(contexts),
                    )
                    background_tasks.add_task(
                        run_eval_bg,
                        final_query_id,
                        request.query,
                        final_answer,
                        contexts,
                        request.document_id,
                    )
            except Exception as e:
                logger.error("SSE stream error", error=str(e))
                error_data = {"detail": str(e)}
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
            background=background_tasks
        )

    # Non-streaming response
    state = await run_agent_pipeline(
        query=request.query,
        document_id=request.document_id,
        db=db,
        user_id=x_user_id,
        conversation_id=conversation_id,
    )
    
    # Run evaluation in background for non-streaming response
    contexts = [c.get("text_snippet", "") for c in state.citations]
    # Extract query_id from the last agent step (stored as string by log_step)
    raw_query_id = (
        state.agent_steps[-1].get("query_id") if state.agent_steps else None
    )
    eval_query_id = uuid.UUID(raw_query_id) if raw_query_id else uuid.uuid4()
    logger.info(
        "DEBUG non-stream eval pre-check",
        citations_count=len(state.citations),
        citations_keys=[list(c.keys()) for c in state.citations[:2]] if state.citations else [],
        contexts_preview=[ctx[:80] for ctx in contexts[:3]],
        contexts_empty=all(not c.strip() for c in contexts) if contexts else True,
        query_id=str(eval_query_id),
    )
    logger.info(
        "Scheduling non-stream eval",
        query_id=str(eval_query_id),
        context_count=len(contexts),
    )
    background_tasks.add_task(
        run_eval_bg, eval_query_id, request.query, state.answer, contexts, request.document_id
    )

    return QueryResponse(
        query_id=state.agent_steps[-1].get("query_id", uuid.uuid4()) if state.agent_steps else uuid.uuid4(),
        query=request.query,
        answer=state.answer,
        citations=[
            {
                "chunk_id": c["chunk_id"],
                "page_number": c.get("page_number"),
                "page_numbers": c.get("page_numbers", []),
                "text_snippet": c.get("text_snippet", ""),
                "relevance_score": c.get("relevance_score", 0),
            }
            for c in state.citations
        ],
        sub_queries=state.sub_queries,
        agent_steps=state.agent_steps,
        latency_ms=state.agent_steps[-1].get("latency_ms", 0) if state.agent_steps else 0,
        cached=False,
        confidence_score=state.confidence_score,
    )

