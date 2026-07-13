"""Knowledge documents API router (Explanation RAG corpus)"""

from typing import Any, Annotated

from fastapi import APIRouter, Depends

from schemas import KnowledgeDocData
from repositories import storage
from routers.dependencies import get_current_user
from logger import material_logger
from analytics.knowledge_docs import ingest_document
from database import async_session_factory

router = APIRouter(prefix="/api/v1/knowledge-docs", tags=["knowledge-docs"])


@router.post("/")
async def create_knowledge_doc(
    data: KnowledgeDocData,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    """Create a knowledge document and chunk+embed its content for Explanation RAG."""
    doc_data = dict(data)
    content = doc_data.pop("content")
    doc_data["user_id"] = current_user["id"]
    doc = await storage.knowledge_docs.create(data=doc_data)

    async with async_session_factory() as session:
        chunk_count = await ingest_document(session, doc["id"], content)

    material_logger.info(f"knowledge_docs.create doc_id={doc['id']} chunks={chunk_count}")
    return {"doc": doc, "chunks_created": chunk_count}


@router.get("/")
async def read_knowledge_docs(current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get all knowledge documents for the current user."""
    docs = await storage.knowledge_docs.get_all(user_id=current_user["id"])

    material_logger.info(f"knowledge_docs.list count={len(docs)}")
    return {"docs": docs}
