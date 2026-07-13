"""Router for lessons"""

from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Depends

from schemas import LessonCreate
from repositories import storage
from routers.dependencies import get_current_user, verify_project_ownership
from logger import lesson_logger

router = APIRouter(prefix="/api/v1/lessons", tags=["lessons"])


@router.post("/")
async def create_lesson(lesson_data: LessonCreate,
                        current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Create a new lesson"""
    await verify_project_ownership(lesson_data.project_id, current_user["id"])
    lesson = await storage.lessons.create(data=dict(lesson_data))
    lesson_logger.info(f"lesson.create lesson={lesson}")
    return {"lesson": lesson}


@router.get("/")
async def read_lessons(project_id: str,
                       current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get all lessons for a project"""
    await verify_project_ownership(project_id, current_user["id"])
    lessons = await storage.lessons.get_by_project(project_id=project_id)
    lesson_logger.info(f"lesson.list project_id={project_id} count={len(lessons)}")
    return {"lessons": lessons}


@router.get("/{lesson_id}")
async def read_lesson(lesson_id: int,
                      current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get a specific lesson"""
    lesson = await storage.lessons.get(lesson_id)
    if not lesson:
        lesson_logger.warning(f"lesson.read_failed lesson_id={lesson_id} error=not_found")
        raise HTTPException(status_code=404, detail="Lesson not found")

    await verify_project_ownership(lesson["project_id"], current_user["id"])
    lesson_logger.info(f"lesson.read lesson_id={lesson_id}")
    return {"lesson": lesson}


@router.patch("/{lesson_id}")
async def update_lesson(lesson_id: int,
                        lesson_data: LessonCreate,
                        current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Update a lesson"""
    lesson = await storage.lessons.get(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    await verify_project_ownership(lesson["project_id"], current_user["id"])
    updated = await storage.lessons.update(lesson_id=lesson_id, data=dict(lesson_data))
    lesson_logger.info(f"lesson.update lesson={updated}")
    return {"lesson": updated}


@router.delete("/{lesson_id}")
async def delete_lesson(lesson_id: int,
                        current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete a lesson"""
    lesson = await storage.lessons.get(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    await verify_project_ownership(lesson["project_id"], current_user["id"])
    await storage.lessons.delete(lesson_id)
    lesson_logger.info(f"lesson.delete lesson_id={lesson_id}")
    return {"status": "deleted"}
