# =============================================================================
# DocuMind — Ingestion Service
# Smart chunking pipeline with parent-child retrieval
# =============================================================================

import uuid
import os
import tiktoken
import structlog
from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.config import settings
from app.models import Document, Chunk
from app.utils.pdf import extract_pdf, PDFExtractionResult, PageContent
from app.services.embeddings import generate_embeddings

logger = structlog.get_logger(__name__)

# Token counter for accurate chunking
tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")


@dataclass
class ChunkData:
    """Intermediate representation of a chunk before DB insertion."""
    content: str
    chunk_index: int
    page_number: Optional[int]
    page_numbers: List[int]
    chunk_kind: str
    start_char: int
    end_char: int
    bbox: Optional[dict] = None
    token_count: int = 0
    parent_index: Optional[int] = None  # index of parent chunk in the list


def count_tokens(text: str) -> int:
    """Count tokens in a text string."""
    return len(tokenizer.encode(text))


def _find_page_for_offset(pages: List[PageContent], char_offset: int) -> Optional[int]:
    """Find which page a character offset belongs to."""
    for page in pages:
        if page.char_offset_start <= char_offset < page.char_offset_end:
            return page.page_number
    return pages[-1].page_number if pages else None


def _find_pages_for_range(
    pages: List[PageContent], start_char: int, end_char: int
) -> List[int]:
    """Find all pages that a character range spans."""
    page_nums = []
    for page in pages:
        # Check if the chunk overlaps with this page
        if page.char_offset_start < end_char and page.char_offset_end > start_char:
            page_nums.append(page.page_number)
    return page_nums or [1]


# =============================================================================
# Recursive Character Splitting with Overlap
# =============================================================================

def _split_text_recursive(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: Optional[List[str]] = None,
) -> List[Tuple[str, int, int]]:
    """
    Recursively split text using a hierarchy of separators.

    Tries to split on the most meaningful boundary first (paragraphs,
    then sentences, then words, then characters).

    Returns:
        List of (chunk_text, start_char, end_char) tuples
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]

    final_chunks: List[Tuple[str, int, int]] = []

    # Find the best separator that exists in the text
    separator = separators[-1]
    for sep in separators:
        if sep in text:
            separator = sep
            break

    # Split text by the chosen separator
    if separator:
        splits = text.split(separator)
    else:
        splits = list(text)

    # Merge splits into chunks of appropriate size
    current_chunk_parts: List[str] = []
    current_start = 0
    running_offset = 0

    for i, split in enumerate(splits):
        # Calculate the actual offset (accounting for separator)
        if i > 0:
            running_offset += len(separator)

        piece_start = running_offset
        running_offset += len(split)

        # Check if adding this split would exceed chunk size
        test_chunk = separator.join(current_chunk_parts + [split]) if current_chunk_parts else split
        test_tokens = count_tokens(test_chunk)

        if test_tokens > chunk_size and current_chunk_parts:
            # Finalize the current chunk
            chunk_text = separator.join(current_chunk_parts)
            chunk_end = piece_start - len(separator)
            final_chunks.append((chunk_text, current_start, chunk_end))

            # Handle overlap: keep trailing parts
            overlap_parts: List[str] = []
            overlap_tokens = 0
            for part in reversed(current_chunk_parts):
                part_tokens = count_tokens(part)
                if overlap_tokens + part_tokens > chunk_overlap:
                    break
                overlap_parts.insert(0, part)
                overlap_tokens += part_tokens

            if overlap_parts:
                # Find the start offset of the overlap
                overlap_text = separator.join(overlap_parts)
                current_start = chunk_end - len(overlap_text)
                current_chunk_parts = overlap_parts + [split]
            else:
                current_start = piece_start
                current_chunk_parts = [split]
        else:
            if not current_chunk_parts:
                current_start = piece_start
            current_chunk_parts.append(split)

    # Don't forget the last chunk
    if current_chunk_parts:
        chunk_text = separator.join(current_chunk_parts)
        final_chunks.append((chunk_text, current_start, running_offset))

    return final_chunks


# =============================================================================
# Parent-Child Chunking Strategy
# =============================================================================

def create_parent_child_chunks(
    extraction: PDFExtractionResult,
) -> List[ChunkData]:
    """
    Implement parent-child chunking strategy:

    1. Split document into LARGE parent chunks (2048 tokens)
    2. Split each parent into SMALL child chunks (512 tokens)
    3. During retrieval: match on small child chunks (precise),
       but return the larger parent chunk (more context for LLM)

    This gives the best of both worlds:
    - Small chunks → better embedding similarity (more precise matching)
    - Large parent chunks → more context for the LLM to generate answers
    """
    all_chunks: List[ChunkData] = []
    chunk_index = 0

    full_text = extraction.full_text

    # Step 1: Create parent chunks (large, ~2048 tokens)
    parent_splits = _split_text_recursive(
        text=full_text,
        chunk_size=settings.parent_chunk_size,
        chunk_overlap=settings.parent_chunk_overlap,
    )

    logger.info("Creating parent-child chunks", parent_count=len(parent_splits))

    for parent_idx, (parent_text, parent_start, parent_end) in enumerate(parent_splits):
        if not parent_text.strip():
            continue

        parent_pages = _find_pages_for_range(extraction.pages, parent_start, parent_end)
        parent_tokens = count_tokens(parent_text)

        # Create parent chunk
        parent_chunk = ChunkData(
            content=parent_text,
            chunk_index=chunk_index,
            page_number=parent_pages[0] if parent_pages else 1,
            page_numbers=parent_pages,
            chunk_kind="parent",
            start_char=parent_start,
            end_char=parent_end,
            token_count=parent_tokens,
        )
        parent_chunk_index = chunk_index
        all_chunks.append(parent_chunk)
        chunk_index += 1

        # Step 2: Split parent into child chunks (small, ~512 tokens)
        child_splits = _split_text_recursive(
            text=parent_text,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

        for child_text, child_rel_start, child_rel_end in child_splits:
            if not child_text.strip():
                continue

            # Convert relative offsets to absolute
            child_abs_start = parent_start + child_rel_start
            child_abs_end = parent_start + child_rel_end
            child_pages = _find_pages_for_range(
                extraction.pages, child_abs_start, child_abs_end
            )

            child_chunk = ChunkData(
                content=child_text,
                chunk_index=chunk_index,
                page_number=child_pages[0] if child_pages else parent_pages[0],
                page_numbers=child_pages,
                chunk_kind="child",
                start_char=child_abs_start,
                end_char=child_abs_end,
                token_count=count_tokens(child_text),
                parent_index=parent_chunk_index,
            )
            all_chunks.append(child_chunk)
            chunk_index += 1

    logger.info(
        "Chunking complete",
        total_chunks=len(all_chunks),
        parent_chunks=sum(1 for c in all_chunks if c.chunk_kind == "parent"),
        child_chunks=sum(1 for c in all_chunks if c.chunk_kind == "child"),
    )

    return all_chunks


# =============================================================================
# Full Ingestion Pipeline
# =============================================================================

async def ingest_document(
    document_id: uuid.UUID,
    file_path: str,
    db: AsyncSession,
) -> None:
    """
    Complete document ingestion pipeline:
    1. Parse PDF → extract text + page info + bounding boxes
    2. Smart chunking → parent-child recursive splitting
    3. Generate embeddings for child chunks
    4. Store everything in PostgreSQL with pgvector

    Args:
        document_id: UUID of the document record
        file_path: Path to the uploaded PDF file
        db: Async database session
    """
    try:
        # ── Step 1: Update status to processing ──────────────────────────
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="processing")
        )
        await db.commit()

        logger.info("Starting ingestion", document_id=str(document_id))

        # ── Step 2: Extract PDF content ──────────────────────────────────
        extraction = extract_pdf(file_path)

        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                page_count=extraction.page_count,
                file_hash=extraction.file_hash,
                metadata_=extraction.metadata,
                status="chunking",
            )
        )
        await db.commit()

        # ── Step 3: Create parent-child chunks ───────────────────────────
        chunk_data_list = create_parent_child_chunks(extraction)

        if not chunk_data_list:
            raise ValueError("No chunks created from document — is the PDF empty?")

        # ── Step 4: Generate embeddings ──────────────────────────────────
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="embedding")
        )
        await db.commit()

        # Only embed child chunks (parents are retrieved via relationship)
        child_chunks = [c for c in chunk_data_list if c.chunk_kind == "child"]
        child_texts = [c.content for c in child_chunks]

        logger.info("Generating embeddings", count=len(child_texts))
        embeddings = await generate_embeddings(child_texts)

        # Map embeddings back to child chunks
        embedding_map = {}
        for i, chunk in enumerate(child_chunks):
            embedding_map[chunk.chunk_index] = embeddings[i]

        # ── Step 5: Store in database ────────────────────────────────────
        # First pass: create all chunks (parents first for FK relationships)
        db_chunks = {}
        parent_chunks_data = [c for c in chunk_data_list if c.chunk_kind == "parent"]
        child_chunks_data = [c for c in chunk_data_list if c.chunk_kind == "child"]

        # Insert parent chunks first
        for chunk_data in parent_chunks_data:
            db_chunk = Chunk(
                document_id=document_id,
                content=chunk_data.content,
                chunk_index=chunk_data.chunk_index,
                page_number=chunk_data.page_number,
                page_numbers=chunk_data.page_numbers,
                chunk_kind=chunk_data.chunk_kind,
                start_char=chunk_data.start_char,
                end_char=chunk_data.end_char,
                token_count=chunk_data.token_count,
                embedding=None,  # Parents don't get embedded
            )
            db.add(db_chunk)
            await db.flush()
            db_chunks[chunk_data.chunk_index] = db_chunk

        # Insert child chunks with parent references and embeddings
        for chunk_data in child_chunks_data:
            parent_db_chunk = db_chunks.get(chunk_data.parent_index)
            embedding = embedding_map.get(chunk_data.chunk_index)

            db_chunk = Chunk(
                document_id=document_id,
                content=chunk_data.content,
                chunk_index=chunk_data.chunk_index,
                page_number=chunk_data.page_number,
                page_numbers=chunk_data.page_numbers,
                chunk_kind=chunk_data.chunk_kind,
                parent_chunk_id=parent_db_chunk.id if parent_db_chunk else None,
                start_char=chunk_data.start_char,
                end_char=chunk_data.end_char,
                token_count=chunk_data.token_count,
                embedding=embedding,
            )
            db.add(db_chunk)
            db_chunks[chunk_data.chunk_index] = db_chunk

        # ── Step 6: Update document status ───────────────────────────────
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status="ready",
                total_chunks=len(chunk_data_list),
            )
        )
        await db.commit()

        logger.info(
            "Ingestion complete",
            document_id=str(document_id),
            total_chunks=len(chunk_data_list),
            pages=extraction.page_count,
        )

    except Exception as e:
        logger.error(
            "Ingestion failed",
            document_id=str(document_id),
            error=str(e),
        )
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status="error",
                error_message=str(e),
            )
        )
        await db.commit()
        raise
