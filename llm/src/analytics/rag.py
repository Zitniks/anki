"""RAG — Retrieval-Augmented Generation (Stage 8, v2).

Retrieval: Hybrid search — vector similarity + BM25 keyword fallback.

Primary:  pgvector cosine similarity on sentence-transformer embeddings
          (semantic search — finds by meaning, not just keywords)
Fallback: PostgreSQL full-text search (BM25) for materials without embeddings

Generation layer: assembled context string for LangGraph chat agent.
"""

from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.embeddings import embed, material_text

_SNIPPET_OPTIONS = "MaxWords=40, MinWords=20, StartSel='**', StopSel='**'"
_MIN_VECTOR_SCORE: float = 0.30   # cosine similarity threshold (0=orthogonal, 1=identical)
_MIN_BM25_RANK: float = 0.01


@dataclass
class RAGChunk:
    material_id: int
    material_name: str
    level: str
    tags: list[str]
    snippet: str
    score: float          # cosine similarity (0–1) or bm25 rank
    search_type: str      # "vector" | "bm25"
    full_content: str


async def search(
    session: AsyncSession,
    query: str,
    user_id: str,
    topic: str | None = None,
    limit: int = 5,
) -> list[RAGChunk]:
    """Hybrid semantic + keyword search over materials.

    1. Embed the query → find top-K by cosine similarity (pgvector)
    2. If fewer than `limit` results → supplement with BM25 keyword search
    3. Deduplicate and return ranked list

    Parameters
    ----------
    session : AsyncSession
    query : str
        Natural-language question or topic string.
    user_id : str
        Restrict to this teacher's materials.
    topic : str or None
        Optional tag filter.
    limit : int
        Max results.

    Returns
    -------
    list[RAGChunk]
        Results sorted by score descending.
    """
    chunks: list[RAGChunk] = []
    seen_ids: set[int] = set()

    # ── Step 1: Vector search ────────────────────────────────────────────────
    try:
        query_vec = embed(query, is_query=True)
        vec_str = "[" + ",".join(str(x) for x in query_vec) + "]"

        topic_clause = "AND m.tags::text ILIKE :topic_pattern" if topic else ""

        vector_sql = text(f"""
            SELECT
                m.id,
                m.name,
                m.level,
                m.tags,
                coalesce(m.content, '') AS full_content,
                1 - (m.embedding <=> (:query_vec)::vector) AS score
            FROM materials m
            WHERE
                m.user_id = :user_id
                AND m.embedding IS NOT NULL
                {topic_clause}
            ORDER BY m.embedding <=> (:query_vec)::vector
            LIMIT :limit
        """)

        params: dict = {"user_id": user_id, "query_vec": vec_str, "limit": limit}
        if topic:
            params["topic_pattern"] = f"%{topic}%"

        result = await session.execute(vector_sql, params)
        for row in result.fetchall():
            if row.score < _MIN_VECTOR_SCORE:
                continue
            chunks.append(RAGChunk(
                material_id=row.id,
                material_name=row.name,
                level=row.level or "",
                tags=row.tags or [],
                snippet=row.full_content[:300],
                score=round(float(row.score), 4),
                search_type="vector",
                full_content=row.full_content,
            ))
            seen_ids.add(row.id)
    except Exception:
        pass   # pgvector not available or no embeddings yet → fall through to BM25

    # ── Step 2: BM25 fallback (fill remaining slots) ─────────────────────────
    if len(chunks) < limit:
        remaining = limit - len(chunks)
        topic_clause = "AND m.tags::text ILIKE :topic_pattern" if topic else ""

        bm25_sql = text(f"""
            SELECT
                m.id,
                m.name,
                m.level,
                m.tags,
                ts_headline(
                    'english',
                    coalesce(m.content, '') || ' ' || coalesce(m.answers, ''),
                    plainto_tsquery('english', :query),
                    :snippet_opts
                ) AS snippet,
                ts_rank(m.content_tsv, plainto_tsquery('english', :query)) AS rank,
                coalesce(m.content, '') AS full_content
            FROM materials m
            WHERE
                m.user_id = :user_id
                AND m.content_tsv @@ plainto_tsquery('english', :query)
                {topic_clause}
            ORDER BY rank DESC
            LIMIT :limit
        """)

        bm25_params: dict = {
            "query": query,
            "user_id": user_id,
            "snippet_opts": _SNIPPET_OPTIONS,
            "limit": remaining + len(seen_ids),   # overfetch to allow dedup
        }
        if topic:
            bm25_params["topic_pattern"] = f"%{topic}%"

        result = await session.execute(bm25_sql, bm25_params)
        for row in result.fetchall():
            if row.id in seen_ids or row.rank < _MIN_BM25_RANK:
                continue
            chunks.append(RAGChunk(
                material_id=row.id,
                material_name=row.name,
                level=row.level or "",
                tags=row.tags or [],
                snippet=row.snippet,
                score=round(float(row.rank), 4),
                search_type="bm25",
                full_content=row.full_content,
            ))
            seen_ids.add(row.id)
            if len(chunks) >= limit:
                break

    return sorted(chunks, key=lambda c: c.score, reverse=True)[:limit]


async def index_material(
    session: AsyncSession,
    material_id: int,
    name: str,
    content: str,
    tags: list[str] | None = None,
) -> None:
    """Compute and store the embedding for one material.

    Called automatically after material creation/update.

    Parameters
    ----------
    session : AsyncSession
    material_id : int
    name : str
    content : str
    tags : list[str] or None
    """
    text_to_embed = material_text(name, content, tags)
    vector = embed(text_to_embed)
    vec_str = "[" + ",".join(str(x) for x in vector) + "]"

    await session.execute(
        text("UPDATE materials SET embedding = (:vec)::vector WHERE id = :id"),
        {"vec": vec_str, "id": material_id},
    )
    await session.commit()


def build_context(chunks: list[RAGChunk], max_chars: int = 3000) -> str:
    """Assemble retrieved chunks into a context block for LLM injection."""
    if not chunks:
        return ""

    lines = ["=== Relevant Study Materials ==="]
    total = 0

    for i, chunk in enumerate(chunks, 1):
        tags_str = ", ".join(chunk.tags) if chunk.tags else "—"
        search_label = "semantic" if chunk.search_type == "vector" else "keyword"
        block = (
            f"\n[{i}] {chunk.material_name} "
            f"(Level: {chunk.level}, Tags: {tags_str}, match: {search_label} {chunk.score:.2f})\n"
            f"{chunk.full_content[:800]}\n"
            f"---"
        )
        if total + len(block) > max_chars:
            break
        lines.append(block)
        total += len(block)

    return "\n".join(lines)
