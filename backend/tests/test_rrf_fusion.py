# =============================================================================
# DocuMind — Unit Tests: Reciprocal Rank Fusion (RRF)
# Tests the core hybrid search merging algorithm
# =============================================================================

import uuid
import pytest
from app.services.search import reciprocal_rank_fusion, SearchHit


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_hit(
    content: str = "test",
    score: float = 1.0,
    search_type: str = "semantic",
    chunk_id: uuid.UUID = None,
) -> SearchHit:
    """Factory for creating SearchHit objects in tests."""
    return SearchHit(
        chunk_id=chunk_id or uuid.uuid4(),
        content=content,
        page_number=1,
        page_numbers=[1],
        score=score,
        search_type=search_type,
    )


# ── Tests ────────────────────────────────────────────────────────────────────

class TestReciprocalRankFusion:
    """Test suite for the RRF merging algorithm."""

    def test_empty_inputs_returns_empty(self):
        """RRF with no inputs should return an empty list."""
        result = reciprocal_rank_fusion([], [])
        assert result == []

    def test_semantic_only(self):
        """When only semantic results exist, RRF should still rank them."""
        hits = [make_hit(f"chunk_{i}", score=1.0 - i * 0.1) for i in range(5)]
        result = reciprocal_rank_fusion(hits, [], top_k=3)

        assert len(result) == 3
        # First result should be the highest-scored semantic hit
        assert result[0].content == "chunk_0"
        # All should be marked hybrid after fusion
        assert all(h.search_type == "hybrid" for h in result)

    def test_keyword_only(self):
        """When only keyword results exist, RRF should still rank them."""
        hits = [make_hit(f"kw_{i}", score=5.0 - i, search_type="keyword") for i in range(4)]
        result = reciprocal_rank_fusion([], hits, top_k=2)

        assert len(result) == 2
        assert result[0].content == "kw_0"

    def test_overlapping_results_get_boosted(self):
        """Chunks appearing in BOTH result sets should rank higher."""
        shared_id = uuid.uuid4()

        semantic = [
            make_hit("shared_chunk", score=0.9, chunk_id=shared_id),
            make_hit("semantic_only", score=0.95),
        ]
        keyword = [
            make_hit("keyword_only", score=5.0, search_type="keyword"),
            make_hit("shared_chunk", score=4.0, search_type="keyword", chunk_id=shared_id),
        ]

        result = reciprocal_rank_fusion(semantic, keyword, top_k=3)

        # The shared chunk should be ranked first because it appears in both lists
        assert result[0].chunk_id == shared_id
        assert result[0].metadata["in_semantic"] is True
        assert result[0].metadata["in_keyword"] is True

    def test_respects_top_k(self):
        """Should never return more than top_k results."""
        semantic = [make_hit(f"s_{i}") for i in range(20)]
        keyword = [make_hit(f"k_{i}", search_type="keyword") for i in range(20)]

        result = reciprocal_rank_fusion(semantic, keyword, top_k=5)
        assert len(result) == 5

    def test_custom_weights(self):
        """Keyword-heavy weight should favor keyword results."""
        s_id = uuid.uuid4()
        k_id = uuid.uuid4()

        semantic = [make_hit("sem", chunk_id=s_id)]
        keyword = [make_hit("kw", search_type="keyword", chunk_id=k_id)]

        # Heavy keyword weight
        result_kw = reciprocal_rank_fusion(
            semantic, keyword,
            semantic_weight=0.1, keyword_weight=0.9, top_k=2,
        )
        # The keyword-only chunk should rank first
        assert result_kw[0].chunk_id == k_id

        # Heavy semantic weight
        result_sem = reciprocal_rank_fusion(
            semantic, keyword,
            semantic_weight=0.9, keyword_weight=0.1, top_k=2,
        )
        assert result_sem[0].chunk_id == s_id

    def test_deduplication_keeps_higher_score(self):
        """When the same chunk appears in both, its scores should be summed."""
        shared_id = uuid.uuid4()

        semantic = [make_hit("dup", chunk_id=shared_id)]
        keyword = [make_hit("dup", search_type="keyword", chunk_id=shared_id)]

        result = reciprocal_rank_fusion(semantic, keyword, top_k=5)

        # Should only appear once in output
        assert len(result) == 1
        assert result[0].chunk_id == shared_id

        # Its RRF score should be higher than either individual score
        solo_semantic = reciprocal_rank_fusion(semantic, [], top_k=1)
        assert result[0].score > solo_semantic[0].score

    def test_scores_are_positive(self):
        """All RRF scores should be positive."""
        semantic = [make_hit(f"s_{i}") for i in range(5)]
        keyword = [make_hit(f"k_{i}", search_type="keyword") for i in range(5)]

        result = reciprocal_rank_fusion(semantic, keyword, top_k=10)
        assert all(h.score > 0 for h in result)

    def test_results_sorted_descending(self):
        """Results should be sorted by RRF score, highest first."""
        semantic = [make_hit(f"s_{i}") for i in range(10)]
        keyword = [make_hit(f"k_{i}", search_type="keyword") for i in range(10)]

        result = reciprocal_rank_fusion(semantic, keyword, top_k=10)
        scores = [h.score for h in result]
        assert scores == sorted(scores, reverse=True)

    def test_metadata_tracks_source(self):
        """Each fused result should track whether it came from semantic, keyword, or both."""
        s_id = uuid.uuid4()
        k_id = uuid.uuid4()

        semantic = [make_hit("sem_only", chunk_id=s_id)]
        keyword = [make_hit("kw_only", search_type="keyword", chunk_id=k_id)]

        result = reciprocal_rank_fusion(semantic, keyword, top_k=2)

        sem_result = next(r for r in result if r.chunk_id == s_id)
        kw_result = next(r for r in result if r.chunk_id == k_id)

        assert sem_result.metadata["in_semantic"] is True
        assert sem_result.metadata["in_keyword"] is False
        assert kw_result.metadata["in_semantic"] is False
        assert kw_result.metadata["in_keyword"] is True
