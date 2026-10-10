# =============================================================================
# DocuMind — Embedding Service
# Generate embeddings using Google Gemini text-embedding-004 (free tier)
# =============================================================================

import structlog
from typing import List
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = structlog.get_logger(__name__)

# Initialize Gemini client
genai.configure(api_key=settings.google_api_key)

# Batch size for embedding API calls (Gemini supports up to 100 per batch)
EMBEDDING_BATCH_SIZE = 100


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
async def _embed_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a batch of texts with retry logic.

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors
    """
    result = genai.embed_content(
        model=settings.embedding_model,
        content=texts,
        task_type="retrieval_document",
    )
    return result["embedding"]


async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts, batching if necessary.

    Handles:
    - Batching for large inputs (100 texts per API call)
    - Automatic retry with exponential backoff
    - Empty/whitespace text filtering

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors (same order as input)
    """
    if not texts:
        return []

    # Clean texts (replace empty strings with a space to avoid API errors)
    cleaned = [t if t.strip() else " " for t in texts]

    all_embeddings: List[List[float]] = []

    # Process in batches
    for i in range(0, len(cleaned), EMBEDDING_BATCH_SIZE):
        batch = cleaned[i : i + EMBEDDING_BATCH_SIZE]
        logger.info(
            "Generating embeddings batch",
            batch_start=i,
            batch_size=len(batch),
            total=len(cleaned),
        )
        batch_embeddings = await _embed_batch(batch)
        all_embeddings.extend(batch_embeddings)

    logger.info("All embeddings generated", total=len(all_embeddings))
    return all_embeddings


async def generate_single_embedding(text: str) -> List[float]:
    """Generate embedding for a single text string (used for queries)."""
    result = genai.embed_content(
        model=settings.embedding_model,
        content=text,
        task_type="retrieval_query",
    )
    return result["embedding"]
