# =============================================================================
# DocuMind — Agent Node: Query Planner
# Analyzes query complexity and decomposes multi-hop questions
# =============================================================================

import json
import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.agent.state import AgentState

logger = structlog.get_logger(__name__)

# LLM for planning
planner_llm = ChatGoogleGenerativeAI(
    model=settings.llm_model,
    google_api_key=settings.google_api_key,
    temperature=0,
)

PLANNER_SYSTEM_PROMPT = """You are a query analysis expert for a document research assistant.

Your job is to analyze the user's question and determine:
1. Whether it is a SIMPLE question (single retrieval) or COMPLEX (needs decomposition)
2. If COMPLEX, decompose it into independent sub-queries that can be answered separately

A question is COMPLEX if it:
- Compares multiple sections/topics
- Requires information from different parts of the document
- Contains multiple distinct questions joined by "and"
- Asks about relationships between concepts in different areas

Respond in valid JSON:
{
    "is_complex": true/false,
    "reasoning": "brief explanation",
    "sub_queries": ["query1", "query2", ...] // only if complex, otherwise empty
}

IMPORTANT: 
- For simple questions, sub_queries should be empty
- Sub-queries should be self-contained and searchable
- Maximum 4 sub-queries
- Each sub-query should focus on one specific aspect"""


async def plan_query(state: AgentState) -> AgentState:
    """
    Query Planner Node — Analyzes query complexity and decomposes if needed.

    For simple queries: passes through directly
    For complex queries (e.g., "Compare X in Ch.3 vs Ch.7"):
        Decomposes into independent sub-queries for parallel retrieval
    """
    query = state.original_query

    logger.info("Planning query", query=query[:100])

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=f"Analyze this question:\n\n{query}"),
    ]

    response = await planner_llm.ainvoke(messages)

    try:
        # Parse the JSON response
        content = response.content
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if isinstance(c, dict) and "text" in c])
        content = content.strip()
        # Handle markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        plan = json.loads(content)

        state.is_complex = plan.get("is_complex", False)
        state.sub_queries = plan.get("sub_queries", [])

        if state.is_complex and state.sub_queries:
            state.current_query = state.sub_queries[0]
            state.log_step(
                "planner",
                f"Complex query decomposed into {len(state.sub_queries)} sub-queries",
                sub_queries=state.sub_queries,
                reasoning=plan.get("reasoning", ""),
            )
            logger.info("Complex query decomposed", sub_queries=state.sub_queries)
        else:
            state.current_query = query
            state.sub_queries = [query]
            state.log_step("planner", "Simple query — direct retrieval")
            logger.info("Simple query — direct retrieval")

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse planner response, treating as simple", error=str(e))
        state.is_complex = False
        state.current_query = query
        state.sub_queries = [query]
        state.log_step("planner", "Parse error — defaulting to simple query")

    return state
