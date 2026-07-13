"""Practice generation helpers for gRPC — a 5-question RAG-grounded MCQ quiz."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from analytics.example_bank import search_examples
from analytics.knowledge_docs import search_explanations
from analytics.rag import build_context, search
from database import async_session_factory
from grpc_svc.session import ResolvedSession
from settings import settings


class PracticeMCQQuestion(BaseModel):
    """One multiple-choice question with its grounded explanation."""

    prompt: str = Field(description="The question text, using the target vocabulary in context.")
    options: list[str] = Field(min_length=4, max_length=4, description="Exactly 4 answer options.")
    correct_index: int = Field(ge=0, le=3, description="Index (0-3) of the correct option.")
    explanation: str = Field(description="1-2 sentences on why the correct option is right.")


class PracticeQuiz(BaseModel):
    """Structured output of the practice-quiz generator."""

    questions: list[PracticeMCQQuestion] = Field(min_length=5, max_length=5)


async def fetch_rag_bundle(user_id: str, query: str) -> dict[str, Any]:
    async with async_session_factory() as session:
        exercise_chunks = await search(session, query, user_id, limit=3)
        example_chunks = await search_examples(session, query, user_id, limit=5)
        explanation_chunks = await search_explanations(session, query, user_id, limit=3)

    sources: list[str] = []
    exercise = build_context(exercise_chunks) if exercise_chunks else ""
    if exercise:
        sources.append("materials")

    examples: list[str] = []
    for chunk in example_chunks:
        line = chunk.sentence
        if chunk.translation:
            line += f" — {chunk.translation}"
        examples.append(line)
    if examples:
        sources.append("examples")

    explanations: list[str] = []
    for chunk in explanation_chunks:
        title = chunk.doc_title or ""
        text = chunk.content or ""
        explanations.append(f"{title}: {text}" if title else text)
    if explanations:
        sources.append("explanations")

    return {
        "exercise": exercise,
        "examples": "\n".join(examples),
        "explanation": "\n---\n".join(explanations),
        "sources": sources,
    }


def build_quiz_prompt(words: list[str], level: str, rag: dict[str, Any]) -> str:
    prompt = (
        f"You are an English tutor. Create a 5-question multiple-choice quiz for CEFR level "
        f"{level}, using target vocabulary: {', '.join(words)}.\n"
        "Each question must have exactly 4 options, one correct answer, and a short explanation "
        "(1-2 sentences) of why that answer is correct — ground the explanation in the reference "
        "material below when it's relevant.\n"
        f"Fresh variant token: {time.time_ns()}.\n"
    )
    if rag.get("exercise"):
        prompt += f"\nRelevant exercise materials:\n{rag['exercise']}"
    if rag.get("examples"):
        prompt += f"\n\nExample sentences:\n{rag['examples']}"
    if rag.get("explanation"):
        prompt += f"\n\nGrammar explanations:\n{rag['explanation']}"
    return prompt


_quiz_generator = settings.llm_cheap.with_structured_output(PracticeQuiz, method="function_calling")

# Yandex's function-calling backend occasionally corrupts quote-like characters inside
# tool-call arguments into C0 control bytes (same root cause as the "/" corruption
# worked around in enrich.py) — strip them defensively from every generated string.
_CONTROL_CHARS = "".join(chr(c) for c in range(0x20) if c not in (0x09, 0x0A, 0x0D))
_CONTROL_TABLE = str.maketrans("", "", _CONTROL_CHARS)


def _clean(text: str) -> str:
    return text.translate(_CONTROL_TABLE).strip()


async def generate_practice(
    session: ResolvedSession,
    words: list[str],
    level: str,
) -> dict[str, Any]:
    query = "english vocabulary practice: " + ", ".join(words)
    rag = await fetch_rag_bundle(session.user_id, query)
    prompt = build_quiz_prompt(words, level or "B1", rag)
    quiz: PracticeQuiz = await _quiz_generator.ainvoke(prompt)
    questions = [
        {
            "prompt": _clean(q.prompt),
            "options": [_clean(opt) for opt in q.options],
            "correct_index": q.correct_index,
            "explanation": _clean(q.explanation),
        }
        for q in quiz.questions
    ]
    return {
        "questions": questions,
        "source": "repetitor",
        "rag_sources": rag["sources"],
    }
