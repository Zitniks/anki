"""LangChain ``BaseRetriever`` adapters over the tutor's per-corpus search functions.

Each retriever wraps an existing ``search_*()`` function behind a uniform
``.ainvoke(query) -> list[Document]`` contract, so ``chat/rag_router.py`` can
call any of them the same way regardless of what runs underneath (hybrid
vector+BM25 SQL, pure vector, or chunk-level vector). The search logic itself
stays in ``analytics/*.py`` — this module only adapts it to LangChain.
"""

from abc import abstractmethod
from collections.abc import Callable

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.example_bank import search_examples
from analytics.knowledge_docs import search_explanations
from analytics.rag import search as search_materials


def reciprocal_rank_fusion(result_sets: list[list[Document]], k: int = 60) -> list[Document]:
    """Merge multiple ranked ``Document`` lists into one, highest combined rank first.

    Shared by ``chat/graph.py``'s ensemble routing and ``chat/search_tools.py``'s
    ``search_all`` tool — both need "query every corpus, merge by rank" and must
    not diverge into two separate implementations of the same fusion logic.
    """
    scores: dict[str, float] = {}
    docs_by_key: dict[str, Document] = {}
    for docs in result_sets:
        for rank, doc in enumerate(docs):
            key = doc.page_content
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            docs_by_key.setdefault(key, doc)
    ranked_keys = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [docs_by_key[key] for key in ranked_keys]


class TutorRetriever(BaseRetriever):
    """Common contract for the tutor's per-corpus retrievers.

    Subclasses implement ``_search()``; this base owns the session lifecycle
    and is async-only (all corpora are queried from LangGraph nodes, never
    from sync code).
    """

    session_factory: Callable[[], AsyncSession]
    user_id: str
    topic: str | None = None
    limit: int = 5

    @abstractmethod
    async def _search(self, session: AsyncSession, query: str) -> list[Document]:
        """Run the corpus-specific search and return LangChain ``Document``s."""

    def _get_relevant_documents(self, query: str) -> list[Document]:
        raise NotImplementedError(f"{type(self).__name__} is async-only — use ainvoke()")

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        async with self.session_factory() as session:
            return await self._search(session, query)


class ExerciseRetriever(TutorRetriever):
    """Exercise RAG — hybrid vector + BM25 over ``materials`` (``analytics/rag.py``)."""

    async def _search(self, session: AsyncSession, query: str) -> list[Document]:
        chunks = await search_materials(session, query, self.user_id, topic=self.topic, limit=self.limit)
        return [
            Document(
                page_content=chunk.full_content,
                metadata={
                    "source": "exercise",
                    "material_id": chunk.material_id,
                    "name": chunk.material_name,
                    "level": chunk.level,
                    "tags": chunk.tags,
                    "score": chunk.score,
                    "search_type": chunk.search_type,
                },
            )
            for chunk in chunks
        ]


class ExampleRetriever(TutorRetriever):
    """Example RAG — pure vector search over ``example_bank`` (``analytics/example_bank.py``)."""

    async def _search(self, session: AsyncSession, query: str) -> list[Document]:
        chunks = await search_examples(session, query, self.user_id, topic=self.topic, limit=self.limit)
        return [
            Document(
                page_content=chunk.sentence,
                metadata={
                    "source": "example",
                    "example_id": chunk.example_id,
                    "topic": chunk.topic,
                    "level": chunk.level,
                    "translation": chunk.translation,
                    "score": chunk.score,
                },
            )
            for chunk in chunks
        ]


class ExplanationRetriever(TutorRetriever):
    """Explanation RAG — chunk-level vector search over ``knowledge_docs``/``knowledge_chunks``."""

    async def _search(self, session: AsyncSession, query: str) -> list[Document]:
        chunks = await search_explanations(session, query, self.user_id, topic=self.topic, limit=self.limit)
        return [
            Document(
                page_content=chunk.content,
                metadata={
                    "source": "explanation",
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "doc_title": chunk.doc_title,
                    "topic": chunk.topic,
                    "level": chunk.level,
                    "chunk_index": chunk.chunk_index,
                    "score": chunk.score,
                },
            )
            for chunk in chunks
        ]
