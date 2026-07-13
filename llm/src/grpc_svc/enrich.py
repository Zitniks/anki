"""AI word enrichment for gRPC (Anki `EnrichWord`).

Vocabulary words are arbitrary, while the Example RAG corpus is scoped to
grammar topics ("present perfect", not "resilient") — so a semantic match is
best-effort, not guaranteed. When `search_examples` returns a hit, its
sentence is passed to the LLM as grounding context; otherwise the LLM
generates the draft from scratch. `source` reflects which path was used.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from analytics.example_bank import search_examples
from database import async_session_factory
from grpc_svc.session import ResolvedSession
from settings import settings


class WordDraft(BaseModel):
    """Structured output of the word enrichment LLM call."""

    translation: str = Field(description="Russian translation of the word, as used in this context/level.")
    example: str = Field(description="An English example sentence using the word, natural for the given CEFR level.")
    transcription: str = Field(
        description="IPA transcription of the word WITHOUT surrounding slashes, e.g. rɪˈzɪliənt.")


_ENRICH_PROMPT = """You are an English tutor helping a student add a vocabulary word to their flashcard deck.

Word: {word}
CEFR level: {level}

Provide a Russian translation, a natural English example sentence using the word, and its IPA transcription.
{grounding}"""

_enricher = settings.llm_cheap.with_structured_output(WordDraft, method="function_calling")

# Yandex's function-calling backend corrupts literal "/" characters inside tool-call
# arguments into \x02 control bytes, so the transcription is generated bare and the
# slashes are added back here.


async def enrich_word(session: ResolvedSession, word: str, level: str) -> dict:
    """Generate a translation/example/transcription draft for a vocabulary word.

    Parameters
    ----------
    session : ResolvedSession
        Resolved caller session (used to scope the Example RAG search).
    word : str
        The vocabulary word to enrich.
    level : str
        CEFR level, e.g. "B1".

    Returns
    -------
    dict
        Keys: translation, example, transcription, source ("rag" | "llm").
    """
    async with async_session_factory() as db_session:
        chunks = await search_examples(db_session, word, session.user_id, limit=1)

    grounding = ""
    source = "llm"
    if chunks and word.lower() in chunks[0].sentence.lower():
        grounding = f"Grammar topic context the student is already studying: {chunks[0].topic}\n" \
            f"Related example sentence for inspiration: {chunks[0].sentence}"
        source = "rag"

    prompt = _ENRICH_PROMPT.format(word=word, level=level or "B1", grounding=grounding)
    draft = await _enricher.ainvoke(prompt)
    transcription = draft.transcription.strip().strip("/")

    return {
        "translation": draft.translation.strip(),
        "example": draft.example.strip(),
        "transcription": f"/{transcription}/" if transcription else "",
        "source": source,
    }
