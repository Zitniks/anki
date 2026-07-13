"""Example RAG — pure vector search over ``example_bank``.

No BM25 fallback: usage-example sentences are short and the corpus is small,
so semantic vector search alone is enough (see ``analytics/rag.py`` for the
hybrid Exercise RAG case where BM25 pulls its weight).
"""

from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.embeddings import embed

_MIN_VECTOR_SCORE: float = 0.30


@dataclass
class ExampleChunk:
    example_id: int
    sentence: str
    topic: str
    level: str
    translation: str | None
    score: float


async def search_examples(
    session: AsyncSession,
    query: str,
    user_id: str,
    topic: str | None = None,
    level: str | None = None,
    limit: int = 5,
) -> list[ExampleChunk]:
    """Semantic search over example sentences.

    Parameters
    ----------
    session : AsyncSession
    query : str
        Natural-language query or grammar topic.
    user_id : str
        Restrict to this teacher's examples.
    topic : str or None
        Optional exact-ish topic filter (ILIKE).
    level : str or None
        Optional CEFR level filter.
    limit : int

    Returns
    -------
    list[ExampleChunk]
        Results sorted by score descending.
    """
    query_vec = embed(query, is_query=True)
    vec_str = "[" + ",".join(str(x) for x in query_vec) + "]"

    filters = ["e.user_id = :user_id", "e.embedding IS NOT NULL"]
    params: dict = {"user_id": user_id, "query_vec": vec_str, "limit": limit}
    if topic:
        filters.append("e.topic ILIKE :topic_pattern")
        params["topic_pattern"] = f"%{topic}%"
    if level:
        filters.append("e.level = :level")
        params["level"] = level

    sql = text(f"""
        SELECT
            e.id, e.sentence, e.topic, e.level, e.translation,
            1 - (e.embedding <=> (:query_vec)::vector) AS score
        FROM example_bank e
        WHERE {" AND ".join(filters)}
        ORDER BY e.embedding <=> (:query_vec)::vector
        LIMIT :limit
    """)

    result = await session.execute(sql, params)
    return [
        ExampleChunk(
            example_id=row.id,
            sentence=row.sentence,
            topic=row.topic,
            level=row.level or "",
            translation=row.translation,
            score=round(float(row.score), 4),
        )
        for row in result.fetchall()
        if row.score >= _MIN_VECTOR_SCORE
    ]


async def index_example(session: AsyncSession, example_id: int, sentence: str, topic: str) -> None:
    """Compute and store the embedding for one example sentence."""
    vector = embed(f"{topic} | {sentence}")
    vec_str = "[" + ",".join(str(x) for x in vector) + "]"

    await session.execute(
        text("UPDATE example_bank SET embedding = (:vec)::vector WHERE id = :id"),
        {"vec": vec_str, "id": example_id},
    )
    await session.commit()
