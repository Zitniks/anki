"""Project API router"""

from typing import Any, Annotated

from fastapi import APIRouter, Depends

from schemas import NotesUpdate
from repositories import storage
from routers.dependencies import get_project_or_404
from logger import note_logger

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("/{project_id}/notes")
async def create_notes(data: NotesUpdate,
                       project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Create notes for a project"""
    project_id = project["id"]
    await storage.projects.update_notes(project_id=project_id, notes=data.notes)
    note_logger.info(f"notes.create project_id={project_id} notes={data.notes}")
    return {"status": "added"}


@router.get("/{project_id}/notes")
async def read_notes(project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Get notes for a project"""
    project_id = project["id"]
    notes = await storage.projects.get_notes(project_id=project_id)
    note_logger.info(f"notes.read project_id={project_id}")
    return {"notes": notes}


@router.delete("/{project_id}/notes")
async def delete_notes(project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Delete notes from a project"""
    project_id = project["id"]
    await storage.projects.update_notes(project_id=project_id, notes=None)
    note_logger.info(f"notes.delete project_id={project_id}")
    return {"status": "deleted"}
