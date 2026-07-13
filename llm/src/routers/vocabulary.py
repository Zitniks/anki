"""Project API router"""

from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Depends

from schemas import VocabularyUpdate
from repositories import storage
from routers.dependencies import get_project_or_404
from logger import vocab_logger

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("/{project_id}/vocabulary")
async def create_vocabulary_item(data: VocabularyUpdate,
                                 project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Add vocabulary items to a project"""
    project_id = project["id"]
    await storage.vocabulary.add_words(project_id, data.items)
    vocabulary = await storage.vocabulary.get_active_by_project(project_id)
    vocab_logger.info(f"vocab.add project_id={project_id} count={len(data.items)} items={list(data.items)}")
    return {"vocabulary": vocabulary}


@router.get("/{project_id}/vocabulary")
async def read_vocabulary(project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Get all vocabulary items for a project"""
    project_id = project["id"]
    vocabulary = await storage.vocabulary.get_active_by_project(project_id)
    vocab_logger.info(f"vocab.read project_id={project_id} count={len(vocabulary)}")
    return {"vocabulary": vocabulary}


@router.delete("/{project_id}/vocabulary/{word_id}")
async def delete_vocabulary_item(word_id: int,
                                 project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Delete a vocabulary item from a project"""
    project_id = project["id"]
    deleted = await storage.vocabulary.soft_delete_by_id(project_id=project_id, word_id=word_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")

    vocabulary = await storage.vocabulary.get_active_by_project(project_id)
    vocab_logger.info(f"vocab.delete project_id={project_id} word_id={word_id}")
    return {"vocabulary": vocabulary}
