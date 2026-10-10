# =============================================================================
# DocuMind — Unit & Integration Tests: Flask Web Frontend & API Gateway
# =============================================================================

import os
import io
import json
import pytest
from unittest.mock import patch, MagicMock
import httpx

# Ensure proper environment configuration
os.environ["FLASK_ENV"] = "testing"
os.environ["BACKEND_API_URL"] = "http://mock-backend:8000"

from frontend.app import app


@pytest.fixture
def client():
    """Create Flask test client."""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.test_client() as client:
        yield client


# ─── UI Routes Tests ─────────────────────────────────────────────────────────

class TestUIRoutes:
    """Test web page routes rendered by Flask."""

    def test_landing_page(self, client):
        """GET / should render the landing page with branding and links."""
        res = client.get("/")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "DocuMind" in html
        assert "Research at the speed of thought" in html
        assert "/chat" in html
        assert "/eval" in html
        assert "/docs" in html

    def test_chat_page(self, client):
        """GET /chat should render the chat workspace with sidebar and dropzone."""
        res = client.get("/chat")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "DocuMind" in html
        assert "pdf-dropzone" in html
        assert "chat-input" in html
        assert "chat-messages" in html
        assert "usage-banner" in html

    def test_eval_page(self, client):
        """GET /eval should render the evaluation dashboard with chart containers."""
        res = client.get("/eval")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Evaluation Dashboard" in html
        assert "radar-svg" in html
        assert "timeline-svg" in html
        assert "eval-metric-card" in html

    def test_docs_page(self, client):
        """GET /docs should render the documentation page."""
        res = client.get("/docs")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "DocuMind Documentation" in html
        assert "Agentic RAG" in html
        assert "API Endpoints Overview" in html


# ─── Static Files Tests ──────────────────────────────────────────────────────

class TestStaticFiles:
    """Test static CSS and JavaScript files exist and are accessible."""

    def test_style_css(self, client):
        """Static style.css should be accessible and non-empty."""
        res = client.get("/static/css/style.css")
        assert res.status_code == 200
        assert "text/css" in res.content_type
        assert len(res.data) > 500

    def test_app_js(self, client):
        """Static app.js should be accessible."""
        res = client.get("/static/js/app.js")
        assert res.status_code == 200
        assert "javascript" in res.content_type

    def test_chat_js(self, client):
        """Static chat.js should be accessible."""
        res = client.get("/static/js/chat.js")
        assert res.status_code == 200
        assert "javascript" in res.content_type

    def test_eval_js(self, client):
        """Static eval.js should be accessible."""
        res = client.get("/static/js/eval.js")
        assert res.status_code == 200
        assert "javascript" in res.content_type


# ─── API Gateway / Proxy Tests ───────────────────────────────────────────────

class TestAPIGateway:
    """Test Flask API proxy endpoints communicating with FastAPI."""

    @patch("frontend.app.httpx.Client")
    def test_health_proxy_connected(self, mock_client_cls, client):
        """GET /api/health returns 200 when backend is healthy."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"status": "healthy", "version": "1.0.0"}
        mock_instance.get.return_value = mock_resp

        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["frontend"] == "healthy"
        assert data["backend_status"] == 200

    @patch("frontend.app.httpx.Client")
    def test_health_proxy_backend_down(self, mock_client_cls, client):
        """GET /api/health returns 503 when backend cannot be reached."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.get.side_effect = httpx.ConnectError("Connection refused")

        res = client.get("/api/health")
        assert res.status_code == 503
        data = res.get_json()
        assert data["backend_status"] == "unreachable"

    def test_upload_rejects_non_pdf(self, client):
        """POST /api/documents/upload should reject non-PDF file formats."""
        data = {
            "file": (io.BytesIO(b"Hello text"), "test.txt"),
        }
        res = client.post(
            "/api/documents/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 400
        json_data = res.get_json()
        assert "Only PDF files are supported" in json_data["detail"]

    def test_upload_rejects_empty_file_field(self, client):
        """POST /api/documents/upload should reject request without file."""
        res = client.post("/api/documents/upload", data={})
        assert res.status_code == 400

    @patch("frontend.app.httpx.Client")
    def test_upload_forwards_pdf(self, mock_client_cls, client):
        """POST /api/documents/upload should forward valid PDF to FastAPI."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(status_code=201, content=b'{"id": "doc-123", "status": "processing"}')
        mock_resp.headers = {"content-type": "application/json"}
        mock_instance.post.return_value = mock_resp

        data = {
            "file": (io.BytesIO(b"%PDF-1.4 mock content"), "sample.pdf"),
        }
        res = client.post(
            "/api/documents/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 201
        assert res.get_json()["id"] == "doc-123"

    @patch("frontend.app.httpx.Client")
    def test_list_documents_proxy(self, mock_client_cls, client):
        """GET /api/documents should forward list request to FastAPI."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(status_code=200, content=b'{"documents": [], "total": 0}')
        mock_resp.headers = {"content-type": "application/json"}
        mock_instance.get.return_value = mock_resp

        res = client.get("/api/documents?skip=0&limit=10")
        assert res.status_code == 200
        assert res.get_json()["total"] == 0

    @patch("frontend.app.httpx.Client")
    def test_delete_document_proxy(self, mock_client_cls, client):
        """DELETE /api/documents/<id> should forward delete request to FastAPI."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(status_code=200, content=b'{"id": "123", "message": "deleted"}')
        mock_resp.headers = {"content-type": "application/json"}
        mock_instance.delete.return_value = mock_resp

        res = client.delete("/api/documents/123")
        assert res.status_code == 200
        assert res.get_json()["id"] == "123"

    def test_query_validation(self, client):
        """POST /api/query validates missing fields."""
        # Empty body
        res = client.post("/api/query", json=None)
        assert res.status_code == 400

        # Missing document_id
        res = client.post("/api/query", json={"query": "test"})
        assert res.status_code == 400
        assert "document_id is required" in res.get_json()["detail"]

        # Empty query
        res = client.post("/api/query", json={"document_id": "doc-1", "query": "  "})
        assert res.status_code == 400
        assert "Query text cannot be empty" in res.get_json()["detail"]

    @patch("frontend.app.httpx.Client")
    def test_query_non_stream_proxy(self, mock_client_cls, client):
        """POST /api/query with stream=false returns JSON response."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(
            status_code=200,
            content=b'{"query_id": "q1", "answer": "Synthesized answer", "citations": []}',
        )
        mock_resp.headers = {"content-type": "application/json"}
        mock_instance.post.return_value = mock_resp

        res = client.post(
            "/api/query",
            json={"document_id": "doc-1", "query": "What is this?", "stream": False},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["answer"] == "Synthesized answer"

    @patch("frontend.app.httpx.Client")
    def test_query_stream_proxy(self, mock_client_cls, client):
        """POST /api/query with stream=true proxies SSE chunks."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance

        # Mock the streaming context manager
        mock_stream_resp = MagicMock()
        mock_stream_resp.status_code = 200
        mock_stream_resp.iter_bytes.return_value = [
            b"event: planning\ndata: {\"step\": \"planning\"}\n\n",
            b"event: token\ndata: {\"token\": \"Hello\"}\n\n",
            b"event: complete\ndata: {\"answer\": \"Hello\"}\n\n",
        ]
        mock_instance.stream.return_value.__enter__.return_value = mock_stream_resp

        res = client.post(
            "/api/query",
            json={"document_id": "doc-1", "query": "Stream test", "stream": True},
        )
        assert res.status_code == 200
        assert "text/event-stream" in res.content_type
        output = res.data.decode("utf-8")
        assert "event: planning" in output
        assert "event: token" in output
        assert "event: complete" in output

    @patch("frontend.app.httpx.Client")
    def test_backend_connection_error_handling(self, mock_client_cls, client):
        """Backend ConnectError should return 503 with helpful explanation."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.get.side_effect = httpx.ConnectError("Connection refused")

        res = client.get("/api/documents")
        assert res.status_code == 503
        data = res.get_json()
        assert "Backend service is unreachable" in data["detail"]
        assert data["error_type"] == "ConnectionError"

    @patch("frontend.app.httpx.Client")
    def test_backend_timeout_handling(self, mock_client_cls, client):
        """Backend TimeoutException should return 504."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.get.side_effect = httpx.TimeoutException("Timed out")

        res = client.get("/api/eval/metrics")
        assert res.status_code == 504
        data = res.get_json()
        assert "timed out" in data["detail"]
        assert data["error_type"] == "Timeout"

    @patch("frontend.app.httpx.Client")
    def test_conversations_proxy(self, mock_client_cls, client):
        """GET /api/conversations should forward to FastAPI."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(status_code=200, content=b'{"conversations": [], "total": 0}')
        mock_resp.headers = {"content-type": "application/json"}
        mock_instance.get.return_value = mock_resp

        res = client.get("/api/conversations?document_id=doc-1")
        assert res.status_code == 200
        assert res.get_json()["total"] == 0

    @patch("frontend.app.httpx.Client")
    def test_usage_proxy(self, mock_client_cls, client):
        """GET /api/usage should forward to FastAPI."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(
            status_code=200,
            content=b'{"tier": "free", "daily_used": 2, "daily_limit": 10, "remaining": 8, "total_queries": 2, "reset_date": "2026-10-10"}',
        )
        mock_resp.headers = {"content-type": "application/json"}
        mock_instance.get.return_value = mock_resp

        res = client.get("/api/usage")
        assert res.status_code == 200
        assert res.get_json()["tier"] == "free"

    @patch("frontend.app.httpx.Client")
    def test_usage_upgrade_proxy(self, mock_client_cls, client):
        """POST /api/usage/upgrade should forward tier change to FastAPI."""
        mock_instance = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_instance
        mock_resp = MagicMock(
            status_code=200,
            content=b'{"user_id": "user1", "tier": "pro", "daily_limit": 999999, "message": "Upgraded"}',
        )
        mock_resp.headers = {"content-type": "application/json"}
        mock_instance.post.return_value = mock_resp

        res = client.post("/api/usage/upgrade", json={"tier": "pro"})
        assert res.status_code == 200
        assert res.get_json()["tier"] == "pro"
