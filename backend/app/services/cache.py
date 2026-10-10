# =============================================================================
# DocuMind — Redis Semantic Cache Service
# Cache similar queries to avoid redundant LLM calls
# =============================================================================

import json
import hashlib
import uuid
import numpy as np
import structlog
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from app.config import settings
from app.services.embeddings import generate_single_embedding

logger = structlog.get_logger(__name__)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))


def _query_hash(query: str, document_id: uuid.UUID) -> str:
    """Generate a deterministic hash for a query + document pair."""
    key = f"{query.strip().lower()}:{str(document_id)}"
    return hashlib.sha256(key.encode()).hexdigest()


class SemanticCache:
    """
    Semantic cache that matches similar queries using embedding similarity.

    Instead of exact-match caching, this finds semantically similar past queries
    and returns cached responses. This saves:
    - LLM API costs (no redundant calls)
    - Latency (instant response from cache)

    Cache keys are stored in Redis as:
    - cache:{hash} → serialized response data
    - cache:embeddings:{document_id} → list of (hash, embedding) pairs for similarity search
    """

    def __init__(self, redis_client):
        self.redis = redis_client
        self.similarity_threshold = settings.cache_similarity_threshold
        self.ttl = settings.cache_ttl_seconds

    async def get(
        self,
        query: str,
        document_id: uuid.UUID,
    ) -> Optional[Dict[str, Any]]:
        """
        Look up a cached response for a similar query.

        Steps:
        1. Check exact match first (fast path)
        2. If no exact match, embed the query and find similar cached queries
        3. Return cached response if similarity > threshold

        Returns:
            Cached response dict or None if no cache hit
        """
        if not self.redis:
            return None

        try:
            # Fast path: exact match
            exact_hash = _query_hash(query, document_id)
            cached = await self.redis.get(f"cache:{exact_hash}")
            if cached:
                logger.info("Cache hit (exact)", query=query[:50])
                await self._increment_hit_count(exact_hash)
                return json.loads(cached)

            # Slow path: semantic similarity search
            query_embedding = await generate_single_embedding(query)

            # Get all cached embeddings for this document
            embeddings_key = f"cache:embeddings:{str(document_id)}"
            cached_entries = await self.redis.lrange(embeddings_key, 0, -1)

            best_match = None
            best_similarity = 0.0

            for entry_json in cached_entries:
                entry = json.loads(entry_json)
                cached_embedding = entry["embedding"]
                similarity = _cosine_similarity(query_embedding, cached_embedding)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = entry

            if best_match and best_similarity >= self.similarity_threshold:
                cached_hash = best_match["hash"]
                cached_response = await self.redis.get(f"cache:{cached_hash}")
                if cached_response:
                    logger.info(
                        "Cache hit (semantic)",
                        query=query[:50],
                        similarity=round(best_similarity, 3),
                    )
                    await self._increment_hit_count(cached_hash)
                    response = json.loads(cached_response)
                    response["cached"] = True
                    response["cache_similarity"] = round(best_similarity, 3)
                    return response

            logger.info("Cache miss", query=query[:50])
            return None

        except Exception as e:
            logger.warning("Cache lookup failed", error=str(e))
            return None

    async def set(
        self,
        query: str,
        document_id: uuid.UUID,
        response_data: Dict[str, Any],
        query_embedding: Optional[List[float]] = None,
    ) -> None:
        """
        Cache a query response with its embedding for semantic matching.

        Args:
            query: Original query text
            document_id: Document UUID
            response_data: Full response to cache
            query_embedding: Pre-computed embedding (optional, will generate if not provided)
        """
        if not self.redis:
            return

        try:
            query_hash = _query_hash(query, document_id)

            # Store the response
            await self.redis.setex(
                f"cache:{query_hash}",
                self.ttl,
                json.dumps(response_data, default=str),
            )

            # Store the embedding for semantic matching
            if query_embedding is None:
                query_embedding = await generate_single_embedding(query)

            embedding_entry = json.dumps({
                "hash": query_hash,
                "query": query,
                "embedding": query_embedding,
                "created_at": datetime.utcnow().isoformat(),
            })

            embeddings_key = f"cache:embeddings:{str(document_id)}"
            await self.redis.lpush(embeddings_key, embedding_entry)

            # Limit the embeddings list size (keep last 500 entries)
            await self.redis.ltrim(embeddings_key, 0, 499)

            # Set TTL on the embeddings list too
            await self.redis.expire(embeddings_key, self.ttl * 2)

            # Track stats
            await self.redis.incr("cache:stats:total_entries")

            logger.info("Cached response", query=query[:50], hash=query_hash[:16])

        except Exception as e:
            logger.warning("Cache set failed", error=str(e))

    async def invalidate_document(self, document_id: uuid.UUID) -> None:
        """Invalidate all cached entries for a document."""
        if not self.redis:
            return

        try:
            embeddings_key = f"cache:embeddings:{str(document_id)}"

            # Get all cached hashes for this document
            entries = await self.redis.lrange(embeddings_key, 0, -1)
            for entry_json in entries:
                entry = json.loads(entry_json)
                await self.redis.delete(f"cache:{entry['hash']}")

            # Delete the embeddings list
            await self.redis.delete(embeddings_key)

            logger.info("Cache invalidated for document", document_id=str(document_id))

        except Exception as e:
            logger.warning("Cache invalidation failed", error=str(e))

    async def _increment_hit_count(self, query_hash: str) -> None:
        """Increment the hit count for cache analytics."""
        try:
            await self.redis.incr(f"cache:hits:{query_hash}")
            await self.redis.incr("cache:stats:total_hits")
        except Exception:
            pass

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        if not self.redis:
            return {"status": "disabled"}

        try:
            total_entries = await self.redis.get("cache:stats:total_entries") or 0
            total_hits = await self.redis.get("cache:stats:total_hits") or 0

            total_entries = int(total_entries)
            total_hits = int(total_hits)

            return {
                "status": "active",
                "total_entries": total_entries,
                "total_hits": total_hits,
                "hit_rate": round(total_hits / max(total_entries, 1) * 100, 1),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
