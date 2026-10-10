# =============================================================================
# DocuMind — Flask Web Application & API Gateway
# Replaces Next.js frontend with Python Flask + Jinja2 + HTML5/CSS/Vanilla JS
# =============================================================================

import os
import json
import uuid
from typing import Generator
import httpx
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    Response,
    stream_with_context,
    session,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "documind-secret-key-change-in-production-2024"
)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB maximum upload limit

# Backend FastAPI URL
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000").rstrip("/")
BACKEND_TIMEOUT = 120.0  # seconds


# ─── Helper Functions ────────────────────────────────────────────────────────

def get_current_user_id() -> str:
    """
    Get or create a persistent user identifier.
    Prioritizes X-User-Id header if sent from the client,
    otherwise uses or initializes a session-based UUID.
    """
    header_user_id = request.headers.get("X-User-Id")
    if header_user_id and header_user_id.strip():
        return header_user_id.strip()

    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
    return session["user_id"]


def build_backend_headers(additional_headers: dict | None = None) -> dict:
    """Build forward headers including user identification."""
    headers = {
        "X-User-Id": get_current_user_id(),
        "Accept": "application/json",
    }
    if additional_headers:
        headers.update(additional_headers)
    return headers


def handle_backend_error(e: Exception) -> tuple[Response, int]:
    """Format user-friendly error response for backend failures."""
    if isinstance(e, httpx.ConnectError):
        return (
            jsonify({
                "detail": (
                    f"Backend service is unreachable at {BACKEND_API_URL}. "
                    "Please ensure the FastAPI service is running."
                ),
                "error_type": "ConnectionError",
            }),
            503,
        )
    elif isinstance(e, httpx.TimeoutException):
        return (
            jsonify({
                "detail": "Request to backend service timed out. The operation may still be processing.",
                "error_type": "Timeout",
            }),
            504,
        )
    else:
        return (
            jsonify({
                "detail": f"Backend communication failure: {str(e)}",
                "error_type": "ProxyError",
            }),
            502,
        )


# ─── UI Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Landing page with branding, hero, workflow visualization, and features."""
    return render_template("index.html")


@app.route("/chat")
def chat():
    """Main chat workspace with PDF upload, conversation threads, and AI Q&A."""
    return render_template("chat.html")


@app.route("/eval")
def eval_dashboard():
    """Evaluation dashboard displaying Ragas metrics and cache statistics."""
    return render_template("eval.html")


@app.route("/docs")
def docs():
    """Documentation page explaining DocuMind architecture and capabilities."""
    return render_template("docs.html")


# ─── Backend API Proxy Routes ────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def proxy_health():
    """
    Health check endpoint: queries backend health and reports frontend status.
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{BACKEND_API_URL}/health")
            data = resp.json() if resp.status_code == 200 else {"status": "degraded"}
            return (
                jsonify({
                    "frontend": "healthy",
                    "backend_url": BACKEND_API_URL,
                    "backend_status": resp.status_code,
                    "backend": data,
                }),
                resp.status_code,
            )
    except Exception as e:
        return (
            jsonify({
                "frontend": "healthy",
                "backend_url": BACKEND_API_URL,
                "backend_status": "unreachable",
                "error": str(e),
            }),
            503,
        )


@app.route("/api/documents/upload", methods=["POST"])
def proxy_upload_document():
    """
    Upload a PDF document.
    Validates file presence, filename extension, and streams upload to backend.
    """
    if "file" not in request.files:
        return jsonify({"detail": "No file field in upload request"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"detail": "No file selected"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"detail": "Only PDF files are supported"}), 400

    try:
        file_bytes = file.read()
        if len(file_bytes) > 50 * 1024 * 1024:
            return jsonify({"detail": "File size exceeds 50MB limit"}), 413

        files = {"file": (file.filename, file_bytes, "application/pdf")}
        headers = {"X-User-Id": get_current_user_id()}

        with httpx.Client(timeout=BACKEND_TIMEOUT) as client:
            resp = client.post(
                f"{BACKEND_API_URL}/api/documents/upload",
                files=files,
                headers=headers,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/documents", methods=["GET"])
def proxy_list_documents():
    """List documents for the current user."""
    try:
        params = {
            "skip": request.args.get("skip", 0),
            "limit": request.args.get("limit", 20),
        }
        headers = build_backend_headers()
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{BACKEND_API_URL}/api/documents",
                params=params,
                headers=headers,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/documents/<document_id>", methods=["GET", "DELETE"])
def proxy_document_detail(document_id: str):
    """Retrieve document details or delete document."""
    try:
        headers = build_backend_headers()
        with httpx.Client(timeout=30.0) as client:
            if request.method == "GET":
                resp = client.get(
                    f"{BACKEND_API_URL}/api/documents/{document_id}",
                    headers=headers,
                )
            else:
                resp = client.delete(
                    f"{BACKEND_API_URL}/api/documents/{document_id}",
                    headers=headers,
                )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/query", methods=["POST"])
def proxy_query():
    """
    Submit a question about a document.
    Supports SSE streaming (stream=true) and standard JSON response (stream=false).
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"detail": "Missing JSON request body"}), 400

    if not payload.get("document_id"):
        return jsonify({"detail": "document_id is required"}), 400

    if not payload.get("query", "").strip():
        return jsonify({"detail": "Query text cannot be empty"}), 400

    headers = build_backend_headers({"Content-Type": "application/json"})
    is_stream = payload.get("stream", False)

    if is_stream:
        # SSE Streaming proxy using generator
        def sse_generator() -> Generator[bytes, None, None]:
            try:
                # Use long timeout for multi-step agent planning and reflection
                with httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0)) as client:
                    with client.stream(
                        "POST",
                        f"{BACKEND_API_URL}/api/query",
                        json=payload,
                        headers=headers,
                    ) as resp:
                        if resp.status_code != 200:
                            err_body = resp.read().decode("utf-8", errors="replace")
                            err_data = {"detail": f"Backend returned {resp.status_code}: {err_body}"}
                            yield f"event: error\ndata: {json.dumps(err_data)}\n\n".encode("utf-8")
                            return

                        for chunk in resp.iter_bytes():
                            yield chunk
            except Exception as e:
                err_data = {"detail": f"Streaming connection error: {str(e)}"}
                yield f"event: error\ndata: {json.dumps(err_data)}\n\n".encode("utf-8")

        return Response(
            stream_with_context(sse_generator()),
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    else:
        # Synchronous JSON response
        try:
            with httpx.Client(timeout=BACKEND_TIMEOUT) as client:
                resp = client.post(
                    f"{BACKEND_API_URL}/api/query",
                    json=payload,
                    headers=headers,
                )
                return Response(
                    resp.content,
                    status=resp.status_code,
                    content_type=resp.headers.get("content-type", "application/json"),
                )
        except Exception as e:
            return handle_backend_error(e)


@app.route("/api/search", methods=["POST"])
def proxy_search():
    """Direct hybrid/semantic/keyword search endpoint."""
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"detail": "Missing JSON request body"}), 400

    try:
        headers = build_backend_headers({"Content-Type": "application/json"})
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BACKEND_API_URL}/api/search",
                json=payload,
                headers=headers,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/conversations", methods=["GET", "POST"])
def proxy_conversations():
    """List or create chat conversation threads."""
    try:
        headers = build_backend_headers({"Content-Type": "application/json"})
        with httpx.Client(timeout=15.0) as client:
            if request.method == "GET":
                resp = client.get(
                    f"{BACKEND_API_URL}/api/conversations",
                    params=request.args,
                    headers=headers,
                )
            else:
                resp = client.post(
                    f"{BACKEND_API_URL}/api/conversations",
                    json=request.get_json(silent=True) or {},
                    headers=headers,
                )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/conversations/<conversation_id>", methods=["GET", "PATCH", "DELETE"])
def proxy_conversation_detail(conversation_id: str):
    """Retrieve message history, rename, or delete a conversation thread."""
    try:
        headers = build_backend_headers({"Content-Type": "application/json"})
        with httpx.Client(timeout=15.0) as client:
            if request.method == "GET":
                resp = client.get(
                    f"{BACKEND_API_URL}/api/conversations/{conversation_id}",
                    headers=headers,
                )
            elif request.method == "PATCH":
                resp = client.patch(
                    f"{BACKEND_API_URL}/api/conversations/{conversation_id}",
                    json=request.get_json(silent=True) or {},
                    headers=headers,
                )
            else:
                resp = client.delete(
                    f"{BACKEND_API_URL}/api/conversations/{conversation_id}",
                    headers=headers,
                )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/eval/metrics", methods=["GET"])
def proxy_eval_metrics():
    """Evaluation dashboard summary and query metrics."""
    try:
        headers = build_backend_headers()
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{BACKEND_API_URL}/api/eval/metrics",
                params=request.args,
                headers=headers,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/eval/cache-stats", methods=["GET"])
def proxy_cache_stats():
    """Retrieve semantic cache statistics from Redis."""
    try:
        headers = build_backend_headers()
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{BACKEND_API_URL}/api/eval/cache-stats",
                headers=headers,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/usage", methods=["GET"])
def proxy_usage():
    """Retrieve rate limiting and query quota usage for the current user."""
    try:
        headers = build_backend_headers()
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{BACKEND_API_URL}/api/usage",
                headers=headers,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


@app.route("/api/usage/upgrade", methods=["POST"])
def proxy_usage_upgrade():
    """Upgrade or downgrade subscription tier."""
    payload = request.get_json(silent=True) or {}
    try:
        headers = build_backend_headers({"Content-Type": "application/json"})
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{BACKEND_API_URL}/api/usage/upgrade",
                json=payload,
                headers=headers,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as e:
        return handle_backend_error(e)


# ─── Main Execution ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() in ("true", "1", "yes")

    print(f"🚀 DocuMind Flask Frontend starting on http://localhost:{port}")
    print(f"🔗 Connected to Backend API at: {BACKEND_API_URL}")
    app.run(host=host, port=port, debug=debug)
