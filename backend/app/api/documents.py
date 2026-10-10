# =============================================================================
# DocuMind — API Routes: Documents
# Handles PDF upload, listing, and management
# =============================================================================

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import uuid
import hashlib
import os
import structlog

from app.database import get_db, async_session
from app.models import Document, DocumentStatus
from app.schemas import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    DocumentDeleteResponse,
)
from app.config import settings
from app.services.ingestion import ingest_document

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


async def run_ingestion_background(document_id: uuid.UUID, file_path: str):
    """
    Run the ingestion pipeline in the background.
    Creates its own database session since FastAPI background tasks
    don't have access to the request-scoped session.
    """
    async with async_session() as db:
        try:
            await ingest_document(document_id, file_path, db)
        except Exception as e:
            logger.error(
                "Background ingestion failed",
                document_id=str(document_id),
                error=str(e),
            )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """
    Upload a PDF document for processing.

    The document goes through: upload → parsing → chunking → embedding → ready
    Processing happens in the background after upload.
    """
    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Validate file size
    content = await file.read()
    file_size = len(content)

    if file_size > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_file_size_mb}MB"
        )

    # Generate file hash for deduplication
    file_hash = hashlib.sha256(content).hexdigest()

    # Check for duplicate uploads
    existing = await db.execute(
        select(Document).where(Document.file_hash == file_hash, Document.user_id == x_user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="This document has already been uploaded"
        )

    # Save file to disk
    stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
    upload_path = os.path.join(settings.upload_dir, stored_filename)
    os.makedirs(settings.upload_dir, exist_ok=True)

    with open(upload_path, "wb") as f:
        f.write(content)

    # Create document record
    document = Document(
        user_id=x_user_id,
        filename=stored_filename,
        original_name=file.filename,
        file_size=file_size,
        file_hash=file_hash,
        status="processing",
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    doc_id = document.id
    logger.info("Document uploaded", document_id=str(doc_id), filename=file.filename)

    # Explicitly commit so the background task can see the document
    await db.commit()

    # Trigger background ingestion pipeline (Phase 2)
    background_tasks.add_task(run_ingestion_background, doc_id, upload_path)

    return DocumentUploadResponse(
        id=doc_id,
        original_name=file.filename,
        status="processing",
        message="Document uploaded successfully. Processing will begin shortly.",
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """List all uploaded documents with pagination."""
    # Get total count
    total_result = await db.execute(select(func.count(Document.id)).where(Document.user_id == x_user_id))
    total = total_result.scalar()

    # Get documents
    result = await db.execute(
        select(Document)
        .where(Document.user_id == x_user_id)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    documents = result.scalars().all()

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(doc) for doc in documents],
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Get a specific document by ID."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == x_user_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    x_user_id: str = Header("anonymous"),
):
    """Delete a document and all its chunks, evaluations, and cached data."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.user_id == x_user_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from disk
    upload_path = os.path.join(settings.upload_dir, document.filename)
    if os.path.exists(upload_path):
        os.remove(upload_path)

    # Delete from DB (cascades to chunks, etc.)
    await db.delete(document)

    logger.info("Document deleted", document_id=str(document_id))

    return DocumentDeleteResponse(
        id=document_id,
        message="Document and all associated data deleted successfully",
    )
