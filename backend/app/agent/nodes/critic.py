# =============================================================================
# DocuMind — Agent Node: Critic (Self-Reflection)
# Evaluates answer quality and triggers re-retrieval if needed
# =============================================================================

import json
import structlog
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.agent.state import AgentState

logger = structlog.get_logger(__name__)

# LLM for self-critique
critic_llm = ChatGoogleGenerativeAI(
    model=settings.llm_model,
    google_api_key=settings.google_api_key,
    temperature=0,
    max_output_tokens=800,
)

CRITIC_SYSTEM_PROMPT = """You are a strict answer quality evaluator for a RAG (Retrieval-Augmented Generation) system.

Your job is to evaluate the generated answer against the source context and check for:

1. **Hallucination**: Does the answer contain claims NOT supported by the sources?
2. **Faithfulness**: Is every claim in the answer grounded in the provided sources?
3. **Completeness**: Does the answer adequately address the original question?
4. **Citation Accuracy**: Are the [Source N] citations correctly matched to the right sources?

Score each dimension from 0.0 to 1.0:
- hallucination_score: 0.0 = no hallucination, 1.0 = completely hallucinated
- faithfulness_score: 0.0 = unfaithful, 1.0 = perfectly faithful
- completeness_score: 0.0 = incomplete, 1.0 = fully complete
- confidence_score: overall quality (0.0 = terrible, 1.0 = excellent)

Respond in valid JSON:
{
    "hallucination_score": 0.0-1.0,
    "faithfulness_score": 0.0-1.0,
    "completeness_score": 0.0-1.0,
    "confidence_score": 0.0-1.0,
    "issues": ["list of specific issues found"],
    "suggested_refinement": "if confidence is low, suggest how to refine the search query"
}"""


CRITIC_HUMAN_TEMPLATE = """## Original Question
{query}

## Retrieved Sources
{context}

## Generated Answer
{answer}

## Evaluate
Check the answer against the sources. Score hallucination, faithfulness, completeness, and overall confidence."""


async def critique_answer(state: AgentState) -> AgentState:
    """
    Critic Node — Self-reflection loop that evaluates answer quality.

    If the hallucination score is above threshold OR confidence is below threshold,
    it triggers re-retrieval with a refined query.

    This is the key differentiator: the agent doesn't just generate answers,
    it VALIDATES them and self-corrects.
    """
    if not state.answer or state.iteration_count >= state.max_iterations:
        state.needs_re_retrieval = False
        state.log_step("critic", "Skipped (no answer or max iterations reached)")
        return state

    logger.info(
        "Critiquing answer",
        iteration=state.iteration_count,
        answer_length=len(state.answer),
    )

    messages = [
        SystemMessage(content=CRITIC_SYSTEM_PROMPT),
        HumanMessage(content=CRITIC_HUMAN_TEMPLATE.format(
            query=state.original_query,
            context=state.retrieval_context,
            answer=state.answer,
        )),
    ]

    response = await critic_llm.ainvoke(messages)

    try:
        content = response.content
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if isinstance(c, dict) and "text" in c])
        content = content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        critique = json.loads(content)

        state.hallucination_score = critique.get("hallucination_score", 0.5)
        state.confidence_score = critique.get("confidence_score", 0.5)
        state.critique_feedback = json.dumps({
            "hallucination": state.hallucination_score,
            "faithfulness": critique.get("faithfulness_score", 0.5),
            "completeness": critique.get("completeness_score", 0.5),
            "confidence": state.confidence_score,
            "issues": critique.get("issues", []),
        })

        # Decision: should we re-retrieve?
        should_retry = (
            state.hallucination_score > settings.hallucination_threshold
            or state.confidence_score < settings.confidence_threshold
        ) and state.iteration_count < state.max_iterations

        state.needs_re_retrieval = should_retry

        if should_retry:
            # Refine the query based on critique
            refinement = critique.get("suggested_refinement", "")
            if refinement:
                state.sub_queries = [refinement]
            else:
                # Add specificity to the original query
                state.sub_queries = [f"{state.original_query} (more specific details)"]

            state.iteration_count += 1

            state.log_step(
                "critic",
                f"Re-retrieval triggered (hallucination={state.hallucination_score:.2f}, "
                f"confidence={state.confidence_score:.2f})",
                hallucination=state.hallucination_score,
                confidence=state.confidence_score,
                refined_query=state.sub_queries[0],
                issues=critique.get("issues", []),
            )
            logger.info(
                "Re-retrieval triggered",
                hallucination=state.hallucination_score,
                confidence=state.confidence_score,
                iteration=state.iteration_count,
            )
        else:
            state.log_step(
                "critic",
                f"Answer accepted (hallucination={state.hallucination_score:.2f}, "
                f"confidence={state.confidence_score:.2f})",
                hallucination=state.hallucination_score,
                confidence=state.confidence_score,
            )
            logger.info(
                "Answer accepted",
                hallucination=state.hallucination_score,
                confidence=state.confidence_score,
            )

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse critique, accepting answer", error=str(e))
        state.needs_re_retrieval = False
        state.confidence_score = 0.7
        state.log_step("critic", "Parse error — accepting answer by default")

    return state
