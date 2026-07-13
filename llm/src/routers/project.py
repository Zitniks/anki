"""Project API router"""

import uuid
import json

from pathlib import Path
from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Depends

from schemas import ProjectCreate
from repositories import storage
from routers.dependencies import get_current_user, get_project_or_404
from logger import project_logger
from settings import settings

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def load_topics_config() -> list:
    """Load topics from JSON config file"""
    config_path = Path(__file__).parents[1] / "config" / "topics.json"
    with open(config_path, encoding="utf-8") as f:
        topics = json.load(f)
    return topics


@router.post("/")
async def create_project(project_data: ProjectCreate,
                         current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Create a new project (the first chat is created automatically)"""
    if settings.MAX_STUDENTS > 0:
        count = await storage.projects.count_by_user(current_user["id"])
        if count >= settings.MAX_STUDENTS:
            raise HTTPException(
                status_code=400,
                detail=f"Student limit of {settings.MAX_STUDENTS} reached.",
            )

    try:
        project = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "name": project_data.name,
            "student_name": project_data.student_name,
            "student_level": project_data.student_level,
            "description": project_data.description,
            "notes": project_data.notes,
        }

        new_project = await storage.projects.create(project)
        project_logger.info(f"project.create project_id={new_project['id']} name={new_project['name']}")

        # Create initial chat
        await storage.chats.create({
            "id": str(uuid.uuid4()),
            "project_id": new_project["id"],
            "name": "Untitled"
        })

        # Add default topics
        default_topics = load_topics_config()["topics"]
        for topic in default_topics:
            topic_data = {"color": "gray", "status": "NOT_STARTED", **topic}
            _ = await storage.topics.create(project_id=new_project["id"], data=topic_data)
            project_logger.info(f"project.topic_add project_id={new_project['id']} topic={topic['topic']}")

        # Get the first chat
        chats = await storage.chats.get_by_project(new_project["id"])

        return {"project": new_project, "first_chat": chats[0] if chats else None}

    except Exception as e:
        project_logger.error(f"project.create_error error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating project") from e


@router.get("/")
async def read_projects(current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get all projects for the current user with chat counts"""
    try:
        projects = await storage.projects.get_all(user_id=current_user["id"])

        for project in projects:
            chats = await storage.chats.get_by_project(project["id"])
            project["chat_count"] = len(chats)
            project["chats"] = chats

        project_logger.info(f"project.list count={len(projects)}")
        return {"projects": projects}

    except Exception as e:
        project_logger.error(f"project.list_error error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching projects") from e


@router.get("/{project_id}")
async def read_project(project: Annotated[dict, Depends(get_project_or_404)], ) -> dict[str, Any]:
    """Get a project by ID with full information"""
    try:
        project_id = project["id"]
        chats = await storage.chats.get_by_project(project_id)
        vocabulary = await storage.vocabulary.get_active_by_project(project_id)
        topics = await storage.topics.get_by_project(project_id)
        notes = await storage.projects.get_notes(project_id)

        project_logger.info(
            f"project.read project_id={project_id} chats={len(chats)} vocab={len(vocabulary)} topics={len(topics)}")
        return {
            "project": project,
            "chats": chats,
            "vocabulary": vocabulary,
            "topics": topics,
            "notes": notes,
        }

    except HTTPException:
        raise
    except Exception as e:
        project_logger.error(f"project.read_error project_id={project['id']} error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching project") from e


@router.patch("/{project_id}")
async def update_project(project_data: ProjectCreate,
                         project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Update project information"""
    try:
        updated_project = await storage.projects.update(project_id=project["id"], data=dict(project_data))
        project_logger.info(f"project.update project_id={project['id']} data={project_data}")
        return updated_project

    except HTTPException:
        raise
    except Exception as e:
        project_logger.error(f"project.update_error project_id={project['id']} error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error updating project") from e


@router.delete("/{project_id}")
async def delete_project(project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Delete a project (removes all chats and messages)"""
    try:
        await storage.projects.delete(project["id"])
        project_logger.info(f"project.delete project_id={project['id']}")
        return {"status": "deleted"}

    except HTTPException:
        raise
    except Exception as e:
        project_logger.error(f"project.delete_error project_id={project['id']} error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting project") from e


@router.get("/{project_id}/stats")
async def get_project_stats(project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Get project statistics"""
    try:
        project_id = project["id"]
        chats = await storage.chats.get_by_project(project_id)
        vocabulary = await storage.vocabulary.get_active_by_project(project_id)
        topics = await storage.topics.get_by_project(project_id)

        total_messages = 0
        for chat in chats:
            messages = await storage.messages.get_by_chat(chat["id"])
            total_messages += len(messages)

        project_logger.info(
            f"project.stats project_id={project_id} chats={len(chats)} messages={total_messages} vocab={len(vocabulary)} topics={len(topics)}"  # noqa: E501
        )
        return {
            "chat_count": len(chats),
            "total_messages": total_messages,
            "vocabulary_count": len(vocabulary),
            "topics_count": len(topics),
            "created_at": project.get("created_at"),
            "updated_at": project.get("updated_at"),
        }

    except HTTPException:
        raise
    except Exception as e:
        project_logger.error(f"project.stats_error project_id={project['id']} error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting project statistics") from e
