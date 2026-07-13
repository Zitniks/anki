"""Explanation RAG — chunked long-form documents (textbooks, articles, notes).

Unlike Exercise/Example RAG, source documents are too long to embed as a
single vector, so they're split into overlapping word chunks at ingestion
time and searched at the chunk level.
"""

import asyncio
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.embeddings import embed, embed_batch

_MIN_VECTOR_SCORE: float = 0.30


def chunk_text(content: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Split *content* into overlapping chunks of ``chunk_size`` words.

    Word count is used as a proxy for tokens — the project has no tokenizer
    dependency, so ``chunk_size=400`` words approximates the "256-512
    tokens" target rather than matching it exactly.

    Parameters
    ----------
    content : str
    chunk_size : int
        Words per chunk.
    overlap : int
        Words shared between consecutive chunks (must be < chunk_size).

    Returns
    -------
    list[str]
        Chunk texts, in document order. Empty input returns ``[]``.
    """
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    words = content.split()
    if not words:
        return []

    step = chunk_size - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start:start + chunk_size])
        chunks.append(chunk)
        if start + chunk_size >= len(words):
            break
    return chunks


async def ingest_document(session: AsyncSession, doc_id: int, content: str) -> int:
    """Chunk *content*, embed each chunk, and store it under *doc_id*.

    Parameters
    ----------
    session : AsyncSession
    doc_id : int
        Existing ``knowledge_docs.id`` to attach chunks to.
    content : str
        Full document text.

    Returns
    -------
    int
        Number of chunks created.
    """
    chunks = chunk_text(content)
    if not chunks:
        return 0

    loop = asyncio.get_event_loop()
    vectors: list[list[float]] = await loop.run_in_executor(None, embed_batch, chunks)

    for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=True)):
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        await session.execute(
            text("""
                INSERT INTO knowledge_chunks (doc_id, chunk_index, content, embedding, created_at)
                VALUES (:doc_id, :chunk_index, :content, (:vec)::vector, now())
            """),
            {"doc_id": doc_id, "chunk_index": i, "content": chunk, "vec": vec_str},
        )

    await session.commit()
    return len(chunks)


@dataclass
class ExplanationChunk:
    chunk_id: int
    doc_id: int
    doc_title: str
    topic: str | None
    level: str | None
    content: str
    chunk_index: int
    score: float


async def search_explanations(
    session: AsyncSession,
    query: str,
    user_id: str,
    topic: str | None = None,
    limit: int = 5,
) -> list[ExplanationChunk]:
    """Chunk-level semantic search over a user's knowledge documents.

    Parameters
    ----------
    session : AsyncSession
    query : str
    user_id : str
        Restrict to this teacher's documents.
    topic : str or None
        Optional topic filter on the parent document.
    limit : int

    Returns
    -------
    list[ExplanationChunk]
        Results sorted by score descending.
    """
    query_vec = embed(query, is_query=True)
    vec_str = "[" + ",".join(str(x) for x in query_vec) + "]"

    filters = ["d.user_id = :user_id", "c.embedding IS NOT NULL"]
    params: dict = {"user_id": user_id, "query_vec": vec_str, "limit": limit}
    if topic:
        filters.append("d.topic ILIKE :topic_pattern")
        params["topic_pattern"] = f"%{topic}%"

    sql = text(f"""
        SELECT
            c.id, c.doc_id, c.chunk_index, c.content,
            d.title AS doc_title, d.topic, d.level,
            1 - (c.embedding <=> (:query_vec)::vector) AS score
        FROM knowledge_chunks c
        JOIN knowledge_docs d ON d.id = c.doc_id
        WHERE {" AND ".join(filters)}
        ORDER BY c.embedding <=> (:query_vec)::vector
        LIMIT :limit
    """)

    result = await session.execute(sql, params)
    return [
        ExplanationChunk(
            chunk_id=row.id,
            doc_id=row.doc_id,
            doc_title=row.doc_title,
            topic=row.topic,
            level=row.level,
            content=row.content,
            chunk_index=row.chunk_index,
            score=round(float(row.score), 4),
        )
        for row in result.fetchall()
        if row.score >= _MIN_VECTOR_SCORE
    ]
