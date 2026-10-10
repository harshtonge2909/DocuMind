# =============================================================================
# DocuMind — Agent Node: Generator
# Synthesizes answers with inline citations from retrieved context
# =============================================================================

import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.agent.state import AgentState

logger = structlog.get_logger(__name__)

# LLM for answer generation
generator_llm = ChatGoogleGenerativeAI(
    model=settings.llm_model,
    google_api_key=settings.google_api_key,
    temperature=0.3,
)

GENERATOR_SYSTEM_PROMPT = """You are DocuMind, an expert research assistant that answers questions based STRICTLY on provided document sources.

CRITICAL RULES:
1. ONLY use information from the provided sources. NEVER use outside knowledge.
2. Cite every claim using [Source N] format (e.g., "The system uses AES-256 encryption [Source 2]").
3. If sources don't contain enough information, say "Based on the available sources, I cannot fully answer this question" and explain what's missing.
4. For complex/comparison questions, structure your answer with clear sections.
5. Be thorough but concise. Prefer quality over quantity.
6. If sources contradict each other, mention both perspectives with their citations.

RESPONSE FORMAT:
- Use markdown formatting for readability
- Include [Source N] citations inline with your text
- Start with a direct answer, then provide supporting details
- End with a brief summary if the answer is long"""


GENERATOR_HUMAN_TEMPLATE = """## Question
{query}

## Retrieved Sources
{context}

## Instructions
Answer the question using ONLY the sources above. Cite every claim with [Source N].
If this is a complex question that was decomposed, synthesize information across all sources into a unified answer."""


async def generate_answer(state: AgentState) -> AgentState:
    """
    Generator Node — Synthesizes a cited answer from retrieved context.

    Takes the retrieved chunks (formatted as numbered sources) and generates
    a comprehensive answer with inline [Source N] citations mapping back
    to specific pages and paragraphs.
    """
    if not state.retrieval_context:
        state.answer = (
            "I couldn't find any relevant information in the document to answer "
            "this question. Please try rephrasing your query or ensure the "
            "document contains relevant content."
        )
        state.log_step("generator", "No context available — empty response")
        return state

    logger.info("Generating answer", query=state.original_query[:100])

    messages = [
        SystemMessage(content=GENERATOR_SYSTEM_PROMPT),
        HumanMessage(content=GENERATOR_HUMAN_TEMPLATE.format(
            query=state.original_query,
            context=state.retrieval_context,
        )),
    ]

    response = await generator_llm.ainvoke(messages)
    content = response.content
    if isinstance(content, list):
        content = " ".join([c.get("text", "") for c in content if isinstance(c, dict) and "text" in c])
    state.answer = content

    # Count citations used
    citation_count = sum(
        1 for i in range(1, len(state.citations) + 1)
        if f"[Source {i}]" in state.answer
    )

    state.log_step(
        "generator",
        f"Generated answer with {citation_count} citations",
        answer_length=len(state.answer),
        citations_used=citation_count,
    )

    logger.info(
        "Answer generated",
        length=len(state.answer),
        citations=citation_count,
    )

    return state
