# =============================================================================
# DocuMind — Application Configuration
# Centralized settings management using Pydantic Settings
# =============================================================================

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ─── App ─────────────────────────────────────────────────────────────
    app_name: str = "DocuMind"
    app_version: str = "1.0.0"
    debug: bool = False

    # ─── Google Gemini (Free Tier) ─────────────────────────────────────
    google_api_key: str = Field(..., description="Google Gemini API key")
    embedding_model: str = "models/text-embedding-004"
    embedding_dimensions: int = 768

    # ─── Groq (Free Tier LLM) ──────────────────────────────────────────
    groq_api_key: str = Field(default="", description="Groq API key")
    
    @property
    def llm_model(self) -> str:
        return "gemini-3.6-flash"

    # ─── Database ────────────────────────────────────────────────────────
    postgres_user: str = "documind"
    postgres_password: str = "documind_secret_2024"
    postgres_db: str = "documind"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str = "postgresql+asyncpg://documind:documind_secret_2024@postgres:5432/documind"

    # ─── Redis ───────────────────────────────────────────────────────────
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_url: str = "redis://redis:6379/0"

    # ─── Payments (Razorpay) ─────────────────────────────────────────────
    razorpay_key_id: str = "rzp_test_TJDZH9yuiPqAOi"
    razorpay_key_secret: str = "77VHW64dKMgeCdUO7ku3I463"

    # ─── Server ──────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_reload: bool = True
    cors_origins: str = '["*"]'

    @property
    def cors_origin_list(self) -> List[str]:
        """Always allow all origins in production to avoid Vercel CORS issues."""
        return ["*"]

    # ─── Search ──────────────────────────────────────────────────────────
    semantic_search_weight: float = 0.6
    bm25_search_weight: float = 0.4
    top_k_results: int = 10
    similarity_threshold: float = 0.7

    # ─── Chunking ────────────────────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 50
    parent_chunk_size: int = 2048
    parent_chunk_overlap: int = 200

    # ─── Agent ───────────────────────────────────────────────────────────
    max_retrieval_iterations: int = 3
    hallucination_threshold: float = 0.7
    confidence_threshold: float = 0.75

    # ─── Cache ───────────────────────────────────────────────────────────
    cache_ttl_seconds: int = 3600
    cache_similarity_threshold: float = 0.92

    # ─── File Upload ─────────────────────────────────────────────────────
    upload_dir: str = "uploads"
    max_file_size_mb: int = 50
    allowed_extensions: List[str] = [".pdf"]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton instance
settings = Settings()
