# 🧠 DocuMind — Flask Frontend

Python Flask web frontend for DocuMind, replacing the legacy Next.js/React interface. Built with HTML5, Jinja2 templates, CSS3, and vanilla JavaScript.

## Architecture

The Flask web application acts as a presentation layer and API gateway:

```
Browser (HTML/CSS/Vanilla JS) 
  → Flask Web Application (Port 5000) 
    → FastAPI Backend API (Port 8000) 
      → LangGraph Agentic RAG Pipeline 
        → PostgreSQL (pgvector) + Redis
```

## Features

- **Landing Page (`/`)**: Product branding, hero intro, agentic workflow visual, feature highlights.
- **Chat Workspace (`/chat`)**: 
  - Drag-and-drop PDF uploader with file validation and status tracking.
  - Multi-turn conversation threads with auto-naming, rename, and delete.
  - Real-time agent status tracker during SSE streaming.
  - Source citations with document snippets and relevance scores.
  - Sub-queries and confidence scores display.
  - Usage quota banner with Free/Pro toggle.
- **Evaluation Dashboard (`/eval`)**: 
  - Ragas metric benchmarks (faithfulness, relevancy, precision, recall, overall).
  - Multi-dimensional SVG radar chart and evaluation trend line chart.
  - Redis semantic cache statistics.
- **Documentation (`/docs`)**: In-depth usage guide and architecture details.

## Local Setup & Development

### 1. Install Dependencies

```bash
cd frontend
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key environment variables:
- `BACKEND_API_URL`: Base URL of the FastAPI backend (default: `http://localhost:8000`).
- `FLASK_HOST`: Bind address (default: `0.0.0.0`).
- `FLASK_PORT`: Local port (default: `5000`).
- `SECRET_KEY`: Flask session security key.

### 3. Run the Development Server

```bash
python app.py
```

Or using the Makefile from project root:

```bash
make dev-frontend
```

The application will be accessible at [http://localhost:5000](http://localhost:5000).

## Running Tests

From the project root:

```bash
pytest frontend/tests
```
