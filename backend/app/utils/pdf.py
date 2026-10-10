# =============================================================================
# DocuMind — PDF Utilities
# Extract text, page info, and bounding boxes from PDFs using PyMuPDF
# =============================================================================

import fitz  # PyMuPDF
import hashlib
import os
import structlog
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = structlog.get_logger(__name__)


@dataclass
class PageContent:
    """Extracted content from a single PDF page."""
    page_number: int           # 1-indexed
    text: str
    char_offset_start: int     # offset in the full document text
    char_offset_end: int
    width: float
    height: float
    word_blocks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PDFExtractionResult:
    """Complete extraction result from a PDF document."""
    full_text: str
    pages: List[PageContent]
    page_count: int
    metadata: Dict[str, Any]
    file_hash: str


def extract_pdf(file_path: str) -> PDFExtractionResult:
    """
    Extract text and structural information from a PDF file.

    Uses PyMuPDF (fitz) for high-quality text extraction with:
    - Per-page text with character offsets
    - Word-level bounding boxes for citation highlighting
    - Document metadata (title, author, etc.)

    Args:
        file_path: Path to the PDF file

    Returns:
        PDFExtractionResult with full text, page data, and metadata
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    doc = fitz.open(file_path)
    pages: List[PageContent] = []
    full_text_parts: List[str] = []
    current_offset = 0

    logger.info("Extracting PDF", path=file_path, pages=doc.page_count)

    for page_num in range(doc.page_count):
        page = doc[page_num]

        # Extract text from the page
        page_text = page.get_text("text")

        # Extract word-level blocks with positions (for highlighting)
        word_blocks = []
        words = page.get_text("words")  # list of (x0, y0, x1, y1, word, block_no, line_no, word_no)
        for w in words:
            word_blocks.append({
                "text": w[4],
                "bbox": {
                    "x0": round(w[0], 2),
                    "y0": round(w[1], 2),
                    "x1": round(w[2], 2),
                    "y1": round(w[3], 2),
                },
                "block_no": w[5],
                "line_no": w[6],
                "word_no": w[7],
            })

        # Build page content with character offsets
        char_start = current_offset
        char_end = current_offset + len(page_text)

        page_content = PageContent(
            page_number=page_num + 1,  # 1-indexed
            text=page_text,
            char_offset_start=char_start,
            char_offset_end=char_end,
            width=page.rect.width,
            height=page.rect.height,
            word_blocks=word_blocks,
        )
        pages.append(page_content)
        full_text_parts.append(page_text)
        current_offset = char_end + 1  # +1 for page separator

    full_text = "\n".join(full_text_parts)

    # Extract document metadata
    metadata = doc.metadata or {}
    clean_metadata = {
        "title": metadata.get("title", ""),
        "author": metadata.get("author", ""),
        "subject": metadata.get("subject", ""),
        "creator": metadata.get("creator", ""),
        "producer": metadata.get("producer", ""),
        "creation_date": metadata.get("creationDate", ""),
        "modification_date": metadata.get("modDate", ""),
    }

    # Compute file hash
    with open(file_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    doc.close()

    logger.info(
        "PDF extracted",
        pages=len(pages),
        total_chars=len(full_text),
        total_words=len(full_text.split()),
    )

    return PDFExtractionResult(
        full_text=full_text,
        pages=pages,
        page_count=len(pages),
        metadata=clean_metadata,
        file_hash=file_hash,
    )


def find_text_bbox_on_page(
    file_path: str,
    page_number: int,
    search_text: str,
) -> Optional[Dict[str, Any]]:
    """
    Find the bounding box of a text snippet on a specific page.
    Used for highlighting citations in the PDF viewer.

    Args:
        file_path: Path to the PDF file
        page_number: 1-indexed page number
        search_text: Text snippet to find

    Returns:
        Bounding box dict or None if not found
    """
    doc = fitz.open(file_path)

    if page_number < 1 or page_number > doc.page_count:
        doc.close()
        return None

    page = doc[page_number - 1]
    instances = page.search_for(search_text)

    doc.close()

    if instances:
        # Return the first match
        rect = instances[0]
        return {
            "x0": round(rect.x0, 2),
            "y0": round(rect.y0, 2),
            "x1": round(rect.x1, 2),
            "y1": round(rect.y1, 2),
            "page": page_number,
        }

    return None
