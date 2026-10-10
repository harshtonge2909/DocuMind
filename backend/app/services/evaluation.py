# =============================================================================
# DocuMind — Ragas Evaluation Service
# Auto-evaluate every query for faithfulness, relevancy, and precision
# =============================================================================

import uuid
import structlog
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.config import settings
from app.models import Evaluation, QueryHistory

logger = structlog.get_logger(__name__)


async def evaluate_query(
    query_id: uuid.UUID,
    query_text: str,
    answer_text: str,
    contexts: List[str],
    document_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[Evaluation]:
    """
    Evaluate a query-answer pair using LLM-based metrics
    (inspired by the Ragas framework).

    Uses Gemini's structured output (via Pydantic) to guarantee valid JSON.
    Retries once on failure.

    Metrics computed:
    - Faithfulness: Is the answer grounded in the context?
    - Answer Relevancy: Does the answer address the question?
    - Context Precision: Are the retrieved contexts relevant?
    - Context Recall: Does the context cover what's needed?
    """
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage
        from pydantic import BaseModel, Field

        # Guard: skip evaluation if no contexts were retrieved
        if not contexts or all(not c.strip() for c in contexts):
            logger.warning(
                "Skipping evaluation — no contexts available",
                query_id=str(query_id),
            )
            return None

        # ── Pydantic schema for guaranteed structured output ─────────────
        class EvalScores(BaseModel):
            faithfulness: float = Field(
                description="Is every claim in the answer supported by the context? 0.0-1.0"
            )
            answer_relevancy: float = Field(
                description="Does the answer directly address the question? 0.0-1.0"
            )
            context_precision: float = Field(
                description="Are the retrieved contexts relevant to the question? 0.0-1.0"
            )
            context_recall: float = Field(
                description="Does the context contain all info needed to answer? 0.0-1.0"
            )

        eval_llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.google_api_key,
            temperature=0,
            max_output_tokens=1024,
        )

        # Use structured output — Gemini returns validated JSON, no parsing needed
        structured_llm = eval_llm.with_structured_output(EvalScores)

        # Limit to top 3 contexts (300 chars each = 900 chars, plenty for eval)
        context_text = "\n\n---\n\n".join(contexts[:3])

        eval_prompt = f"""You are an evaluation expert for RAG (Retrieval-Augmented Generation) systems.

Evaluate the following query-answer pair against the provided context.

## Query
{query_text}

## Answer
{answer_text}

## Retrieved Context
{context_text}

Score each metric from 0.0 to 1.0:
1. faithfulness: Is every claim in the answer supported by the context? (1.0 = fully faithful)
2. answer_relevancy: Does the answer directly address the question? (1.0 = perfectly relevant)
3. context_precision: Are the retrieved contexts relevant to the question? (1.0 = all relevant)
4. context_recall: Does the context contain all information needed to answer? (1.0 = complete coverage)"""

        # ── Invoke with single retry ─────────────────────────────────────
        scores = None
        for attempt in range(2):  # max 2 attempts
            try:
                scores = await structured_llm.ainvoke([HumanMessage(content=eval_prompt)])
                if scores:
                    break
            except Exception as retry_err:
                logger.warning(
                    "Eval LLM attempt failed",
                    attempt=attempt + 1,
                    error=str(retry_err),
                    query_id=str(query_id),
                )
                if attempt == 1:
                    raise  # re-raise on second failure

        if not scores:
            logger.error("Eval LLM returned None after retries", query_id=str(query_id))
            return None

        faithfulness = max(0.0, min(1.0, scores.faithfulness))
        answer_relevancy = max(0.0, min(1.0, scores.answer_relevancy))
        context_precision = max(0.0, min(1.0, scores.context_precision))
        context_recall = max(0.0, min(1.0, scores.context_recall))

        # Weighted overall score
        overall = (
            faithfulness * 0.35 +
            answer_relevancy * 0.30 +
            context_precision * 0.20 +
            context_recall * 0.15
        )

        evaluation = Evaluation(
            query_id=query_id,
            document_id=document_id,
            faithfulness=round(faithfulness, 3),
            answer_relevancy=round(answer_relevancy, 3),
            context_precision=round(context_precision, 3),
            context_recall=round(context_recall, 3),
            overall_score=round(overall, 3),
            eval_metadata={
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
                "context_precision": context_precision,
                "context_recall": context_recall,
            },
        )

        db.add(evaluation)
        await db.commit()
        await db.refresh(evaluation)

        logger.info(
            "Evaluation complete",
            query_id=str(query_id),
            faithfulness=faithfulness,
            relevancy=answer_relevancy,
            precision=context_precision,
            recall=context_recall,
            overall=overall,
        )

        return evaluation

    except Exception as e:
        logger.exception("Evaluation FAILED — full traceback", query_id=str(query_id), error=str(e))
        return None


async def get_evaluation_metrics(
    db: AsyncSession,
    document_id: Optional[uuid.UUID] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Get aggregated evaluation metrics for the dashboard.

    Returns summary statistics and individual evaluation records.
    """
    # Build query
    query = select(Evaluation).order_by(desc(Evaluation.created_at)).limit(limit)
    if document_id:
        query = query.where(Evaluation.document_id == document_id)

    result = await db.execute(query)
    evaluations = result.scalars().all()

    if not evaluations:
        return {
            "summary": {
                "total_queries": 0,
                "avg_faithfulness": None,
                "avg_answer_relevancy": None,
                "avg_context_precision": None,
                "avg_context_recall": None,
                "avg_overall_score": None,
            },
            "evaluations": [],
            "timeline": [],
        }

    # Compute averages
    faithfulness_scores = [e.faithfulness for e in evaluations if e.faithfulness is not None]
    relevancy_scores = [e.answer_relevancy for e in evaluations if e.answer_relevancy is not None]
    precision_scores = [e.context_precision for e in evaluations if e.context_precision is not None]
    recall_scores = [e.context_recall for e in evaluations if e.context_recall is not None]
    overall_scores = [e.overall_score for e in evaluations if e.overall_score is not None]

    avg = lambda scores: round(sum(scores) / len(scores), 3) if scores else None

    summary = {
        "total_queries": len(evaluations),
        "avg_faithfulness": avg(faithfulness_scores),
        "avg_answer_relevancy": avg(relevancy_scores),
        "avg_context_precision": avg(precision_scores),
        "avg_context_recall": avg(recall_scores),
        "avg_overall_score": avg(overall_scores),
    }

    # Timeline data for charts
    timeline = [
        {
            "date": e.created_at.isoformat() if e.created_at else None,
            "faithfulness": e.faithfulness,
            "answer_relevancy": e.answer_relevancy,
            "context_precision": e.context_precision,
            "context_recall": e.context_recall,
            "overall_score": e.overall_score,
            "query_id": str(e.query_id),
        }
        for e in evaluations
    ]

    # Individual evaluations
    eval_list = [
        {
            "id": str(e.id),
            "query_id": str(e.query_id),
            "document_id": str(e.document_id) if e.document_id else None,
            "faithfulness": e.faithfulness,
            "answer_relevancy": e.answer_relevancy,
            "context_precision": e.context_precision,
            "context_recall": e.context_recall,
            "overall_score": e.overall_score,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in evaluations
    ]

    return {
        "summary": summary,
        "evaluations": eval_list,
        "timeline": timeline,
    }
