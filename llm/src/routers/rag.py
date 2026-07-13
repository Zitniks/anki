"""RAG router — Stage 8 v2 (hybrid vector + BM25) + Example/Explanation RAG."""

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.rag import search, build_context, index_material
from analytics.example_bank import search_examples
from analytics.knowledge_docs import search_explanations
from analytics.embeddings import embed_batch, material_text
from database import async_session_factory
from routers.dependencies import get_current_user, get_project_or_404

router = APIRouter(prefix="/api/v1/projects", tags=["rag"])


async def _get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


@router.get("/{project_id}/rag/search")
async def rag_search(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(_get_session)],
    q: str = Query(..., min_length=2, description="Search query"),
    topic: str | None = Query(default=None, description="Optional topic filter"),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """Search materials using hybrid vector + BM25 search.

    Primary: semantic vector similarity (pgvector cosine).
    Fallback: full-text BM25 for materials not yet embedded.
    """
    user_id = str(current_user["id"])
    chunks = await search(session, q, user_id, topic=topic, limit=limit)
    context = build_context(chunks)

    return {
        "project_id": project["id"],
        "query": q,
        "results": [
            {
                "material_id": c.material_id,
                "name": c.material_name,
                "level": c.level,
                "tags": c.tags,
                "snippet": c.snippet,
                "score": c.score,
                "search_type": c.search_type,
            }
            for c in chunks
        ],
        "context": context,
        "total_found": len(chunks),
    }


@router.get("/{project_id}/rag/context")
async def rag_context(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(_get_session)],
    q: str = Query(..., min_length=2),
    topic: str | None = Query(default=None),
    limit: int = Query(default=3, ge=1, le=10),
) -> dict[str, Any]:
    """Return only the assembled context string for injection into LLM prompt."""
    user_id = str(current_user["id"])
    chunks = await search(session, q, user_id, topic=topic, limit=limit)
    context = build_context(chunks)

    return {
        "project_id": project["id"],
        "query": q,
        "context": context,
        "sources": [
            {
                "material_id": c.material_id,
                "name": c.material_name,
                "score": c.score,
                "search_type": c.search_type,
            }
            for c in chunks
        ],
    }


@router.get("/{project_id}/rag/example")
async def rag_example(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(_get_session)],
    q: str = Query(..., min_length=2, description="Search query"),
    topic: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """Search example sentences using pure vector search (Example RAG)."""
    user_id = str(current_user["id"])
    chunks = await search_examples(session, q, user_id, topic=topic, limit=limit)

    return {
        "project_id": project["id"],
        "query": q,
        "results": [
            {
                "example_id": c.example_id,
                "sentence": c.sentence,
                "topic": c.topic,
                "level": c.level,
                "translation": c.translation,
                "score": c.score,
            }
            for c in chunks
        ],
        "total_found": len(chunks),
    }


@router.get("/{project_id}/rag/explanation")
async def rag_explanation(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(_get_session)],
    q: str = Query(..., min_length=2, description="Search query"),
    topic: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """Search knowledge document chunks using vector search (Explanation RAG)."""
    user_id = str(current_user["id"])
    chunks = await search_explanations(session, q, user_id, topic=topic, limit=limit)

    return {
        "project_id": project["id"],
        "query": q,
        "results": [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "doc_title": c.doc_title,
                "topic": c.topic,
                "level": c.level,
                "content": c.content,
                "score": c.score,
            }
            for c in chunks
        ],
        "total_found": len(chunks),
    }


async def _reindex_materials(session: AsyncSession, user_id: str, force: bool) -> dict[str, Any]:
    where = "WHERE user_id = :uid" + ("" if force else " AND embedding IS NULL")
    rows = await session.execute(
        text(f"SELECT id, name, coalesce(content,'') AS content, tags FROM materials {where}"),
        {"uid": user_id},
    )
    materials = rows.fetchall()
    if not materials:
        return {"indexed": 0, "skipped": 0, "message": "Nothing to index."}

    texts = [material_text(m.name, m.content, m.tags or []) for m in materials]
    loop = asyncio.get_event_loop()
    vectors: list[list[float]] = await loop.run_in_executor(None, embed_batch, texts)

    for m, vec in zip(materials, vectors, strict=True):
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        await session.execute(
            text("UPDATE materials SET embedding = (:vec)::vector WHERE id = :id"),
            {"vec": vec_str, "id": m.id},
        )
    await session.commit()
    return {
        "indexed": len(materials),
        "skipped": 0 if force else "unknown",
        "message": f"Indexed {len(materials)} material(s).",
    }


async def _reindex_examples(session: AsyncSession, user_id: str, force: bool) -> dict[str, Any]:
    where = "WHERE user_id = :uid" + ("" if force else " AND embedding IS NULL")
    rows = await session.execute(
        text(f"SELECT id, sentence, topic FROM example_bank {where}"),
        {"uid": user_id},
    )
    examples = rows.fetchall()
    if not examples:
        return {"indexed": 0, "skipped": 0, "message": "Nothing to index."}

    texts = [f"{e.topic} | {e.sentence}" for e in examples]
    loop = asyncio.get_event_loop()
    vectors: list[list[float]] = await loop.run_in_executor(None, embed_batch, texts)

    for e, vec in zip(examples, vectors, strict=True):
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        await session.execute(
            text("UPDATE example_bank SET embedding = (:vec)::vector WHERE id = :id"),
            {"vec": vec_str, "id": e.id},
        )
    await session.commit()
    return {
        "indexed": len(examples),
        "skipped": 0 if force else "unknown",
        "message": f"Indexed {len(examples)} example(s).",
    }


async def _reindex_explanations(session: AsyncSession, user_id: str, force: bool) -> dict[str, Any]:
    where = "WHERE d.user_id = :uid" + ("" if force else " AND c.embedding IS NULL")
    rows = await session.execute(
        text(f"""
            SELECT c.id, c.content FROM knowledge_chunks c
            JOIN knowledge_docs d ON d.id = c.doc_id
            {where}
        """),
        {"uid": user_id},
    )
    chunks = rows.fetchall()
    if not chunks:
        return {"indexed": 0, "skipped": 0, "message": "Nothing to index."}

    texts = [c.content for c in chunks]
    loop = asyncio.get_event_loop()
    vectors: list[list[float]] = await loop.run_in_executor(None, embed_batch, texts)

    for c, vec in zip(chunks, vectors, strict=True):
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        await session.execute(
            text("UPDATE knowledge_chunks SET embedding = (:vec)::vector WHERE id = :id"),
            {"vec": vec_str, "id": c.id},
        )
    await session.commit()
    return {
        "indexed": len(chunks),
        "skipped": 0 if force else "unknown",
        "message": f"Indexed {len(chunks)} chunk(s).",
    }


@router.post("/{project_id}/rag/reindex")
async def rag_reindex(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(_get_session)],
    force: bool = Query(default=False, description="Re-embed even already-indexed rows"),
    corpus: Literal["exercise", "example", "explanation"] = Query(
        default="exercise", description="Which RAG corpus to re-index"),
) -> dict[str, Any]:
    """Batch re-index one RAG corpus for this user into the vector store.

    Computes sentence-transformer embeddings and stores them in the corpus's
    `embedding` column. Idempotent when `force=False` (skips rows that
    already have an embedding). `corpus` defaults to `exercise` — unchanged
    behavior for existing callers.

    Use after:
    - Initial setup (seeding existing materials/examples/documents)
    - Upgrading the embedding model
    """
    user_id = str(current_user["id"])
    if corpus == "example":
        return await _reindex_examples(session, user_id, force)
    if corpus == "explanation":
        return await _reindex_explanations(session, user_id, force)
    return await _reindex_materials(session, user_id, force)
