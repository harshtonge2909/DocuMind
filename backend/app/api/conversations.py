# =============================================================================
# DocuMind — API Routes: Conversations
# CRUD for chat history threads
# =============================================================================

import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.database import get_db
from app.models import Conversation, QueryHistory
from app.schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
    MessageResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Create a new conversation thread for a document."""
    conversation = Conversation(
        user_id=x_user_id,
        document_id=request.document_id,
        title=request.title or "New Chat",
    )
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)

    logger.info(
        "Conversation created",
        conversation_id=str(conversation.id),
        document_id=str(request.document_id),
    )

    return ConversationResponse(
        id=conversation.id,
        document_id=conversation.document_id,
        title=conversation.title,
        message_count=0,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    document_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """List conversations for the current user, optionally filtered by document."""
    base_filter = [Conversation.user_id == x_user_id]
    if document_id:
        base_filter.append(Conversation.document_id == document_id)

    # Total count
    total_result = await db.execute(
        select(func.count(Conversation.id)).where(*base_filter)
    )
    total = total_result.scalar()

    # Fetch conversations with message counts
    result = await db.execute(
        select(Conversation)
        .where(*base_filter)
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    conversations = result.scalars().all()

    # Get message counts in bulk
    conv_ids = [c.id for c in conversations]
    count_result = await db.execute(
        select(
            QueryHistory.conversation_id,
            func.count(QueryHistory.id).label("msg_count"),
        )
        .where(QueryHistory.conversation_id.in_(conv_ids))
        .group_by(QueryHistory.conversation_id)
    )
    counts = {row[0]: row[1] for row in count_result.all()}

    return ConversationListResponse(
        conversations=[
            ConversationResponse(
                id=c.id,
                document_id=c.document_id,
                title=c.title,
                message_count=counts.get(c.id, 0),
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in conversations
        ],
        total=total,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Get a conversation with its full message history."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == x_user_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from sqlalchemy.orm import selectinload

    # Fetch messages ordered by time, eagerly loading evaluations
    msg_result = await db.execute(
        select(QueryHistory)
        .options(selectinload(QueryHistory.evaluation))
        .where(QueryHistory.conversation_id == conversation_id)
        .order_by(QueryHistory.created_at.asc())
    )
    query_records = msg_result.scalars().all()

    # Convert query records into interleaved user/assistant messages
    messages: list[MessageResponse] = []
    for qh in query_records:
        # User message
        messages.append(MessageResponse(
            id=qh.id,
            role="user",
            content=qh.query_text,
            citations=[],
            sub_queries=[],
            confidence_score=None,
            latency_ms=None,
            cached=False,
            created_at=qh.created_at,
        ))
        # Assistant message (if answer exists)
        if qh.answer_text:
            messages.append(MessageResponse(
                id=qh.id,
                role="assistant",
                content=qh.answer_text,
                citations=qh.citations or [],
                sub_queries=qh.sub_queries or [],
                confidence_score=qh.evaluation.overall_score if qh.evaluation else None,
                latency_ms=qh.latency_ms,
                cached=qh.cached,
                created_at=qh.created_at,
            ))

    return ConversationDetailResponse(
        id=conversation.id,
        document_id=conversation.document_id,
        title=conversation.title,
        messages=messages,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    request: ConversationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Rename a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == x_user_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.title = request.title
    await db.flush()
    await db.refresh(conversation)

    # Get message count
    count_result = await db.execute(
        select(func.count(QueryHistory.id)).where(
            QueryHistory.conversation_id == conversation_id
        )
    )
    msg_count = count_result.scalar()

    return ConversationResponse(
        id=conversation.id,
        document_id=conversation.document_id,
        title=conversation.title,
        message_count=msg_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == x_user_id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conversation)

    logger.info("Conversation deleted", conversation_id=str(conversation_id))

    return {"id": str(conversation_id), "message": "Conversation deleted"}
