# =============================================================================
# DocuMind — Schemas Package
# =============================================================================

from app.schemas.document import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    DocumentDeleteResponse,
)
from app.schemas.query import (
    Citation,
    QueryRequest,
    QueryResponse,
    SearchRequest,
    SearchResult,
    SearchResponse,
)
from app.schemas.evaluation import (
    EvaluationResponse,
    EvaluationSummary,
    EvaluationDashboardResponse,
    CacheStatsResponse,
)
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
    MessageResponse,
)

__all__ = [
    "DocumentResponse",
    "DocumentListResponse",
    "DocumentUploadResponse",
    "DocumentDeleteResponse",
    "Citation",
    "QueryRequest",
    "QueryResponse",
    "SearchRequest",
    "SearchResult",
    "SearchResponse",
    "EvaluationResponse",
    "EvaluationSummary",
    "EvaluationDashboardResponse",
    "CacheStatsResponse",
    "ConversationCreate",
    "ConversationResponse",
    "ConversationDetailResponse",
    "ConversationListResponse",
    "ConversationUpdateRequest",
    "MessageResponse",
]

