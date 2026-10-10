# =============================================================================
# DocuMind — Test Fixtures & Configuration
# Shared fixtures for all tests — no external services required
# =============================================================================

import sys
import os
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# ── Ensure the app module is importable ──────────────────────────────────────
# We patch settings before any app import to avoid requiring a real .env file
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Mock Settings (no .env required) ────────────────────────────────────────
# Set these before any imports to prevent global Settings() initialization from crashing
os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Provide mock settings so tests don't need a real .env or database."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///test.db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


# ── Sample Data Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def sample_document_id():
    return uuid.UUID("2ab5f3f7-1dea-4716-99d5-acb2a202f31a")


@pytest.fixture
def sample_query_id():
    return uuid.UUID("6a1b2027-ac13-4e9d-b974-3b9fb56a677e")


@pytest.fixture
def sample_chunks():
    """Generate realistic chunk data for testing."""
    return [
        {
            "content": "Machine learning models can be categorized into supervised, "
                       "unsupervised, and reinforcement learning paradigms. Supervised "
                       "learning requires labeled training data.",
            "page_number": 3,
            "page_numbers": [3],
            "chunk_index": 0,
        },
        {
            "content": "Neural networks consist of layers of interconnected nodes. "
                       "Deep learning refers to networks with many hidden layers, "
                       "enabling hierarchical feature extraction.",
            "page_number": 5,
            "page_numbers": [5, 6],
            "chunk_index": 1,
        },
        {
            "content": "The transformer architecture, introduced in 'Attention Is All "
                       "You Need' (Vaswani et al., 2017), revolutionized NLP by "
                       "replacing recurrence with self-attention mechanisms.",
            "page_number": 12,
            "page_numbers": [12],
            "chunk_index": 2,
        },
        {
            "content": "Retrieval-Augmented Generation (RAG) combines information "
                       "retrieval with language generation to produce factually "
                       "grounded responses without fine-tuning the model.",
            "page_number": 18,
            "page_numbers": [18, 19],
            "chunk_index": 3,
        },
        {
            "content": "BM25 is a ranking function used in information retrieval. "
                       "It extends TF-IDF by incorporating document length "
                       "normalization and term frequency saturation.",
            "page_number": 22,
            "page_numbers": [22],
            "chunk_index": 4,
        },
    ]


@pytest.fixture
def sample_query():
    return "How do transformer models work in NLP?"


@pytest.fixture
def sample_answer():
    return (
        "Transformer models use self-attention mechanisms instead of recurrence "
        "to process sequences [Source 1]. The architecture was introduced in "
        "'Attention Is All You Need' (Vaswani et al., 2017) [Source 3]. "
        "This approach enables parallelization and captures long-range "
        "dependencies more effectively than RNNs [Source 2]."
    )


@pytest.fixture
def sample_contexts():
    return [
        "The transformer architecture, introduced in 'Attention Is All "
        "You Need' (Vaswani et al., 2017), revolutionized NLP.",
        "Neural networks consist of layers of interconnected nodes.",
        "Machine learning models can be categorized into supervised learning.",
    ]
