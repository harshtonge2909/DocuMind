# =============================================================================
# DocuMind — API Router
# Aggregates all route modules into a single router
# =============================================================================

from fastapi import APIRouter

from app.api.documents import router as documents_router
from app.api.query import router as query_router
from app.api.search import router as search_router
from app.api.evaluation import router as evaluation_router
from app.api.conversations import router as conversations_router
from app.api.usage import router as usage_router
from app.api.payments import router as payments_router

api_router = APIRouter(prefix="/api")

api_router.include_router(documents_router)
api_router.include_router(query_router)
api_router.include_router(search_router)
api_router.include_router(evaluation_router)
api_router.include_router(conversations_router)
api_router.include_router(usage_router)
api_router.include_router(payments_router)
