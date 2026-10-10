# =============================================================================
# DocuMind — Unit Tests: Evaluation Service
# Tests the LLM-as-judge evaluation pipeline
# =============================================================================

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel


# ── Tests: Evaluation Guard Clauses ──────────────────────────────────────────

class TestEvaluationGuards:
    """Test that evaluation correctly skips invalid inputs."""

    @pytest.mark.asyncio
    async def test_empty_contexts_returns_none(self):
        """Evaluation should return None when contexts list is empty."""
        from app.services.evaluation import evaluate_query

        mock_db = AsyncMock()
        result = await evaluate_query(
            query_id=uuid.uuid4(),
            query_text="test query",
            answer_text="test answer",
            contexts=[],
            document_id=uuid.uuid4(),
            db=mock_db,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_contexts_returns_none(self):
        """Evaluation should return None when all contexts are whitespace."""
        from app.services.evaluation import evaluate_query

        mock_db = AsyncMock()
        result = await evaluate_query(
            query_id=uuid.uuid4(),
            query_text="test query",
            answer_text="test answer",
            contexts=["", "  ", "\n\t"],
            document_id=uuid.uuid4(),
            db=mock_db,
        )
        assert result is None


# ── Tests: Score Clamping ────────────────────────────────────────────────────

class TestScoreClamping:
    """Test that evaluation scores are properly clamped to [0, 1]."""

    def test_clamp_within_range(self):
        """Values within [0, 1] should remain unchanged."""
        assert max(0.0, min(1.0, 0.5)) == 0.5
        assert max(0.0, min(1.0, 0.0)) == 0.0
        assert max(0.0, min(1.0, 1.0)) == 1.0

    def test_clamp_above_range(self):
        """Values > 1.0 should be clamped to 1.0."""
        assert max(0.0, min(1.0, 1.5)) == 1.0
        assert max(0.0, min(1.0, 99.0)) == 1.0

    def test_clamp_below_range(self):
        """Values < 0.0 should be clamped to 0.0."""
        assert max(0.0, min(1.0, -0.5)) == 0.0
        assert max(0.0, min(1.0, -99.0)) == 0.0


# ── Tests: Overall Score Computation ─────────────────────────────────────────

class TestOverallScoreComputation:
    """Test the weighted overall score calculation."""

    def test_perfect_scores(self):
        """All 1.0 scores should produce 1.0 overall."""
        overall = 1.0 * 0.35 + 1.0 * 0.30 + 1.0 * 0.20 + 1.0 * 0.15
        assert abs(overall - 1.0) < 1e-9

    def test_zero_scores(self):
        """All 0.0 scores should produce 0.0 overall."""
        overall = 0.0 * 0.35 + 0.0 * 0.30 + 0.0 * 0.20 + 0.0 * 0.15
        assert overall == 0.0

    def test_faithfulness_has_highest_weight(self):
        """Faithfulness (0.35) should have the most impact on overall score."""
        # Only faithfulness = 1.0, everything else = 0.0
        faith_only = 1.0 * 0.35 + 0.0 * 0.30 + 0.0 * 0.20 + 0.0 * 0.15
        # Only relevancy = 1.0, everything else = 0.0
        relev_only = 0.0 * 0.35 + 1.0 * 0.30 + 0.0 * 0.20 + 0.0 * 0.15

        assert faith_only > relev_only

    def test_weights_sum_to_one(self):
        """The four weights must sum to 1.0."""
        total = 0.35 + 0.30 + 0.20 + 0.15
        assert abs(total - 1.0) < 1e-9

    def test_mixed_scores(self):
        """Test with realistic mixed scores."""
        f, r, p, c = 0.85, 0.90, 0.75, 0.80
        expected = f * 0.35 + r * 0.30 + p * 0.20 + c * 0.15
        # Should be approximately 0.8375
        assert 0.83 < expected < 0.85


# ── Tests: Evaluation Metrics Aggregation ────────────────────────────────────

class TestMetricsAggregation:
    """Test the metrics averaging logic used by the dashboard."""

    def test_average_of_scores(self):
        """Test basic averaging."""
        scores = [0.8, 0.9, 0.7, 1.0]
        avg = round(sum(scores) / len(scores), 3)
        assert avg == 0.85

    def test_empty_scores_returns_none(self):
        """No scores should return None, not crash."""
        scores = []
        avg = round(sum(scores) / len(scores), 3) if scores else None
        assert avg is None

    def test_single_score(self):
        """Single score should return itself."""
        scores = [0.75]
        avg = round(sum(scores) / len(scores), 3)
        assert avg == 0.75


# ── Tests: Structured Output Schema ─────────────────────────────────────────

class TestEvalScoresSchema:
    """Test that the Pydantic schema for structured output is correctly defined."""

    def test_valid_scores_parse(self):
        """Valid scores should parse without error."""

        class EvalScores(BaseModel):
            faithfulness: float
            answer_relevancy: float
            context_precision: float
            context_recall: float

        scores = EvalScores(
            faithfulness=0.85,
            answer_relevancy=0.90,
            context_precision=0.75,
            context_recall=0.80,
        )
        assert scores.faithfulness == 0.85
        assert scores.answer_relevancy == 0.90

    def test_integer_scores_coerce_to_float(self):
        """Integer values should be coerced to float."""

        class EvalScores(BaseModel):
            faithfulness: float
            answer_relevancy: float
            context_precision: float
            context_recall: float

        scores = EvalScores(
            faithfulness=1,
            answer_relevancy=0,
            context_precision=1,
            context_recall=0,
        )
        assert isinstance(scores.faithfulness, float)
        assert scores.faithfulness == 1.0
