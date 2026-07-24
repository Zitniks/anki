"""Agentic RAG search tools.

Thin LangChain-tool wrappers over the existing per-corpus retrievers
(``analytics/retrievers.py``) — no new data-access paths, no changes to
``TutorRetriever`` or the corpus structure. Bound alongside the regular
action tools (``chat/tools.py::TOOLS``) in ``chat/graph.py``'s single model
call, so the agent can call either kind of tool freely.
"""

import asyncio
import time

from langchain.tools import ToolRuntime, tool
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from analytics.retrievers import (
    ExampleRetriever,
    ExerciseRetriever,
    ExplanationRetriever,
    TutorRetriever,
    reciprocal_rank_fusion,
)
from chat.state import TutorRuntimeContext
from database import async_session_factory
from logger import llm_logger

_MAX_FRAGMENT_CHARS = 400
_SENTENCE_SEPARATORS = (". ", "! ", "? ", "\n")

# Yandex's function-calling backend corrupts literal "/" characters inside
# tool-call arguments into C0 control bytes (same root cause worked around in
# grpc_svc/enrich.py and grpc_svc/practice.py). The original "/" is
# unrecoverable by the time it reaches us, so — same defensive posture as
# practice.py::_clean — we just strip the resulting control byte rather than
# let it reach the embedding model or logs as raw noise.
_CONTROL_CHARS = "".join(chr(c) for c in range(0x20) if c not in (0x09, 0x0A, 0x0D))
_CONTROL_TABLE = str.maketrans("", "", _CONTROL_CHARS)


def _clean_query(text: str) -> str:
    return text.translate(_CONTROL_TABLE).strip()


def _truncate(text: str, max_chars: int = _MAX_FRAGMENT_CHARS) -> str:
    """Truncate to at most `max_chars`, preferring a sentence boundary."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    best_cut = -1
    for sep in _SENTENCE_SEPARATORS:
        idx = window.rfind(sep)
        if idx > best_cut:
            best_cut = idx + len(sep)
    if best_cut > max_chars * 0.4:
        return window[:best_cut].strip()
    return window.rstrip() + "…"


def _format_hits(docs: list[Document], empty_label: str, *, show_source: bool = False) -> str:
    if not docs:
        return f"По этому запросу {empty_label} не найдено."
    lines = []
    for i, doc in enumerate(docs, 1):
        prefix = f"[{doc.metadata.get('source', '?')}] " if show_source else ""
        lines.append(f"{i}. {prefix}{_truncate(doc.page_content)}")
    return "\n".join(lines)


def _log_search(corpus: str, query: str, docs: list[Document], elapsed_ms: float) -> None:
    top_score = docs[0].metadata.get("score") if docs else None
    llm_logger.info(
        f"search_tool.query corpus={corpus} query={query!r} count={len(docs)} "
        f"top_score={top_score} elapsed_ms={elapsed_ms:.0f}")


async def _search_one(retriever: TutorRetriever, query: str, corpus: str) -> list[Document] | None:
    """Run one retriever, logging and swallowing errors (returns None on failure)."""
    t0 = time.monotonic()
    try:
        docs = await retriever.ainvoke(query)
    except Exception as e:
        llm_logger.error(f"search_tool.error corpus={corpus} query={query!r} error={e}", exc_info=True)
        return None
    _log_search(corpus, query, docs, (time.monotonic() - t0) * 1000)
    return docs


class SearchExplanationsInput(BaseModel):
    topic: str = Field(description="Грамматическое правило или тема для поиска объяснения")
    limit: int = Field(default=5, ge=1, le=10)


@tool("search_explanations", args_schema=SearchExplanationsInput)
async def search_explanations_tool(
    topic: str,
    runtime: ToolRuntime[TutorRuntimeContext],
    limit: int = 5,
) -> str:
    """Найти объяснение грамматического правила или темы.
    Используй, когда студент спрашивает почему, как устроено, в чём разница."""
    ctx = runtime.context
    clean_topic = _clean_query(topic)
    retriever = ExplanationRetriever(
        session_factory=async_session_factory, user_id=str(ctx.user_id), topic=clean_topic, limit=limit)
    docs = await _search_one(retriever, clean_topic, "explanation")
    if docs is None:
        return "Поиск объяснений временно недоступен."
    return _format_hits(docs, "объяснений")


class SearchExamplesInput(BaseModel):
    query: str = Field(description="Слово или конструкция, для которой нужны примеры употребления")
    limit: int = Field(default=5, ge=1, le=10)


@tool("search_examples", args_schema=SearchExamplesInput)
async def search_examples_tool(
    query: str,
    runtime: ToolRuntime[TutorRuntimeContext],
    limit: int = 5,
) -> str:
    """Найти примеры употребления слова или конструкции в живых предложениях."""
    ctx = runtime.context
    clean = _clean_query(query)
    retriever = ExampleRetriever(session_factory=async_session_factory, user_id=str(ctx.user_id), limit=limit)
    docs = await _search_one(retriever, clean, "example")
    if docs is None:
        return "Поиск примеров временно недоступен."
    return _format_hits(docs, "примеров")


class SearchExercisesInput(BaseModel):
    query: str = Field(description="Тема или запрос для поиска готового упражнения")
    level: str | None = Field(default=None, description="Уровень CEFR (A1-C2), если известен")
    limit: int = Field(default=5, ge=1, le=10)


@tool("search_exercises", args_schema=SearchExercisesInput)
async def search_exercises_tool(
    query: str,
    runtime: ToolRuntime[TutorRuntimeContext],
    level: str | None = None,
    limit: int = 5,
) -> str:
    """Найти готовые упражнения по теме. level принимает значения CEFR от A1 до C2."""
    ctx = runtime.context
    clean = _clean_query(query)
    # ExerciseRetriever/TutorRetriever has no `level` field (deliberately not
    # extended — task forbids changing TutorRetriever/corpus structure), so
    # the level is folded into the search text itself: the hybrid vector+BM25
    # search over `materials` already embeds each material's tags (see
    # analytics/embeddings.py::material_text), so a level-tagged material
    # scores higher when the query text also carries the level — a soft
    # signal, not a hard filter.
    effective_query = f"{clean} (уровень {level})" if level else clean
    retriever = ExerciseRetriever(session_factory=async_session_factory, user_id=str(ctx.user_id), limit=limit)
    docs = await _search_one(retriever, effective_query, "exercise")
    if docs is None:
        return "Поиск упражнений временно недоступен."
    return _format_hits(docs, "упражнений")


class SearchAllInput(BaseModel):
    query: str = Field(description="Поисковый запрос, когда неясно, к какой категории он относится")
    limit: int = Field(default=5, ge=1, le=10)


async def run_search_all(user_id: str, query: str, limit: int = 5) -> str:
    """Core of ``search_all`` — also called directly by ``chat/graph.py``'s
    ``_finalize`` (skip-search safety net, Этап 4), which has no
    ``ToolRuntime`` to hand to the ``@tool``-wrapped version."""
    clean = _clean_query(query)
    retrievers: list[TutorRetriever] = [
        ExerciseRetriever(session_factory=async_session_factory, user_id=user_id, limit=limit),
        ExplanationRetriever(session_factory=async_session_factory, user_id=user_id, limit=limit),
        ExampleRetriever(session_factory=async_session_factory, user_id=user_id, limit=limit),
    ]
    t0 = time.monotonic()
    try:
        result_sets = await asyncio.gather(*(r.ainvoke(clean) for r in retrievers))
    except Exception as e:
        llm_logger.error(f"search_tool.error corpus=all query={clean!r} error={e}", exc_info=True)
        return "Поиск временно недоступен."
    docs = reciprocal_rank_fusion(list(result_sets))[:limit]
    _log_search("all", clean, docs, (time.monotonic() - t0) * 1000)
    return _format_hits(docs, "результатов", show_source=True)


@tool("search_all", args_schema=SearchAllInput)
async def search_all_tool(
    query: str,
    runtime: ToolRuntime[TutorRuntimeContext],
    limit: int = 5,
) -> str:
    """Искать сразу во всех корпусах. Используй, когда непонятно,
    к какой категории относится вопрос."""
    return await run_search_all(str(runtime.context.user_id), query, limit)


SEARCH_TOOLS = [search_explanations_tool, search_examples_tool, search_exercises_tool, search_all_tool]
_SEARCH_TOOL_NAMES = {t.name for t in SEARCH_TOOLS}
_SEARCH_TOOL_CORPUS = {
    "search_explanations": "explanation",
    "search_examples": "example",
    "search_exercises": "exercise",
    "search_all": "all",
}
