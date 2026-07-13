"""Error explanation for gRPC (Anki `ExplainError`).

Anki only has an isolated word + what the student typed, no chat context —
so this mirrors `practice.py`'s shape (RAG context, then a free-text LLM
call via `complete_chat`) rather than `enrich.py`'s structured-output
pattern, since the output here is prose, not fixed fields. Writes go to
`practice_chat_id` (like `GeneratePractice`), keeping auto-generated
content out of the student's visible chat history.
"""

from __future__ import annotations

from typing import Any

from analytics.knowledge_docs import search_explanations
from database import async_session_factory
from grpc_svc.session import ResolvedSession


async def fetch_explanation_context(user_id: str, word: str, expected: str, got: str) -> list[str]:
    query = f"{word}: expected '{expected}', got '{got}'"
    async with async_session_factory() as db_session:
        chunks = await search_explanations(db_session, query, user_id, limit=3)
    return [f"{c.doc_title}: {c.content}" if c.doc_title else c.content for c in chunks]


def build_explain_prompt(word: str, expected: str, got: str, sentence: str, explanations: list[str]) -> str:
    prompt = (
        f"You are an English tutor. The student was practicing the word '{word}'.\n"
        f"Expected answer: {expected}\n"
        f"Student's answer: {got}\n"
    )
    if sentence:
        prompt += f"Sentence context: {sentence}\n"
    if explanations:
        prompt += "\nRelevant grammar explanations:\n" + "\n---\n".join(explanations)
    prompt += (
        "\n\nExplain briefly and clearly why the student's answer was wrong and what the correct "
        "rule is. 2-4 sentences, no markdown fences."
    )
    return prompt


async def explain_error(
    session: ResolvedSession,
    word: str,
    expected: str,
    got: str,
    sentence: str,
    complete_chat,
) -> dict[str, Any]:
    explanations = await fetch_explanation_context(session.user_id, word, expected, got)
    prompt = build_explain_prompt(word, expected, got, sentence, explanations)
    text = await complete_chat(session, session.practice_chat_id, prompt)
    return {
        "explanation": text.strip(),
        "source": "rag" if explanations else "llm",
    }
