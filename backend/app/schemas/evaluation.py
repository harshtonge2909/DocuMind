# =============================================================================
# DocuMind — Pydantic Schemas: Evaluation
# Request/Response schemas for evaluation endpoints
# =============================================================================

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID


class EvaluationResponse(BaseModel):
    """Ragas evaluation metrics for a single query."""
    id: UUID
    query_id: UUID
    document_id: Optional[UUID] = None
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    context_recall: Optional[float] = None
    overall_score: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvaluationSummary(BaseModel):
    """Aggregated evaluation metrics."""
    total_queries: int
    avg_faithfulness: Optional[float] = None
    avg_answer_relevancy: Optional[float] = None
    avg_context_precision: Optional[float] = None
    avg_context_recall: Optional[float] = None
    avg_overall_score: Optional[float] = None


class EvaluationDashboardResponse(BaseModel):
    """Full dashboard data with timeline and summary."""
    summary: EvaluationSummary
    evaluations: List[EvaluationResponse]
    timeline: List[Dict[str, Any]] = []  # For chart data


class CacheStatsResponse(BaseModel):
    """Cache performance statistics."""
    total_entries: int
    total_hits: int
    hit_rate: Optional[float] = None
    avg_latency_saved_ms: Optional[float] = None
    estimated_cost_saved: Optional[float] = None
