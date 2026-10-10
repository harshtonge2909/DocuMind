# =============================================================================
# DocuMind — Agent State Definition
# Defines the shared state flowing through the LangGraph agent
# =============================================================================

from typing import List, Optional, Dict, Any, Annotated
from uuid import UUID
from dataclasses import dataclass, field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


@dataclass
class AgentState:
    """
    State that flows through the LangGraph agent pipeline.

    Each node reads from and writes to this shared state.
    """
    # ─── Input ───────────────────────────────────────────────────────────
    original_query: str = ""
    document_id: Optional[UUID] = None

    # ─── Query Planning ──────────────────────────────────────────────────
    is_complex: bool = False
    sub_queries: List[str] = field(default_factory=list)
    current_query: str = ""     # The query currently being processed

    # ─── Retrieval ───────────────────────────────────────────────────────
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_context: str = ""  # Formatted context for LLM

    # ─── Generation ──────────────────────────────────────────────────────
    answer: str = ""
    citations: List[Dict[str, Any]] = field(default_factory=list)

    # ─── Self-Critique ───────────────────────────────────────────────────
    confidence_score: float = 0.0
    hallucination_score: float = 0.0
    critique_feedback: str = ""
    needs_re_retrieval: bool = False

    # ─── Flow Control ────────────────────────────────────────────────────
    iteration_count: int = 0
    max_iterations: int = 3
    agent_steps: List[Dict[str, Any]] = field(default_factory=list)

    # ─── Messages (for LangGraph compatibility) ──────────────────────────
    messages: Annotated[List[BaseMessage], add_messages] = field(default_factory=list)

    def log_step(self, node: str, detail: str, **kwargs):
        """Log an agent step for transparency/debugging."""
        step = {
            "node": node,
            "detail": detail,
            "iteration": self.iteration_count,
            **kwargs,
        }
        self.agent_steps.append(step)
