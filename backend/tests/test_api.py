# =============================================================================
# DocuMind — Integration Tests: FastAPI API Endpoints
# Tests the REST API using httpx AsyncClient (no real DB)
# =============================================================================

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


# ── Fixtures ─────────────────────────────────────────────────────────────────

class MockResult:
    def scalars(self):
        return self
    def all(self):
        return []
    def first(self):
        return None
    def scalar(self):
        return 0

@pytest.fixture
def mock_db_session():
    """Create a mock async database session."""
    session = AsyncMock()
    # When execute is awaited, return our sync MockResult
    session.execute.return_value = MockResult()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def app(mock_db_session):
    """Import the FastAPI app with mocked dependencies."""
    from app.main import app
    from app.database import get_db

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    
    # Also patch the health check so it doesn't try to query SQLite for pgvector
    with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
        mock_health.return_value = {"status": "healthy", "pgvector_version": "0.5.0"}
        yield app
    
    # Clean up overrides after test
    app.dependency_overrides.clear()


# ── Tests: Health Endpoint ───────────────────────────────────────────────────

class TestHealthEndpoint:
    """Test the /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, app):
        """Health endpoint should always return 200."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data


# ── Tests: Root Endpoint ────────────────────────────────────────────────────

class TestRootEndpoint:
    """Test the root / endpoint."""

    @pytest.mark.asyncio
    async def test_root_returns_200(self, app):
        """Root endpoint should return API info."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data or "app" in data or "version" in data


# ── Tests: Documents Endpoint ────────────────────────────────────────────────

class TestDocumentsEndpoint:
    """Test the /api/documents endpoints."""

    @pytest.mark.asyncio
    async def test_list_documents_returns_200(self, app):
        """GET /api/documents should return a list."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/documents",
                headers={"X-User-Id": "test-user"},
            )

        # Should return 200 even if empty
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_rejects_non_pdf(self, app):
        """POST /api/documents/upload should reject non-PDF files."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/documents/upload",
                files={"file": ("test.txt", b"not a pdf", "text/plain")},
                headers={"X-User-Id": "test-user"},
            )

        # Should reject with 400
        assert response.status_code == 400


# ── Tests: Query Endpoint ────────────────────────────────────────────────────

class TestQueryEndpoint:
    """Test the /api/query endpoint."""

    @pytest.mark.asyncio
    async def test_query_requires_document_id(self, app):
        """POST /api/query without document_id should fail validation."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/query",
                json={"query": "test question"},
                headers={"X-User-Id": "test-user"},
            )

        # Should return 422 (validation error) because document_id is required
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_query_requires_query_text(self, app):
        """POST /api/query without query text should fail validation."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/query",
                json={"document_id": str(uuid.uuid4())},
                headers={"X-User-Id": "test-user"},
            )

        assert response.status_code == 422


# ── Tests: Eval Endpoint ────────────────────────────────────────────────────

class TestEvalEndpoint:
    """Test the /api/eval endpoints."""

    @pytest.mark.asyncio
    async def test_eval_metrics_returns_200(self, app):
        """GET /api/eval/metrics should return evaluation data."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/eval/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data or "evaluations" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_eval_cache_stats_returns_200(self, app):
        """GET /api/eval/cache-stats should return cache statistics."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/eval/cache-stats")

        assert response.status_code == 200


# ── Tests: Search Endpoint ──────────────────────────────────────────────────

class TestSearchEndpoint:
    """Test the /api/search endpoint."""

    @pytest.mark.asyncio
    async def test_search_requires_query(self, app):
        """POST /api/search without query should fail."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/search",
                json={"document_id": str(uuid.uuid4())},
                headers={"X-User-Id": "test-user"},
            )

        assert response.status_code == 422
