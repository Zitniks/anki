"""Project API router"""

from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Depends

from schemas import TopicUpdate
from repositories import storage
from routers.dependencies import get_project_or_404
from logger import topic_logger

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("/{project_id}/topics")
async def create_topic(data: TopicUpdate,
                       project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Add a new topic to a project"""
    project_id = project["id"]
    topic = await storage.topics.create(project_id=project_id, data=dict(data))
    topic_logger.info(f"topic.create project_id={project_id} topic={topic}")
    topics = await storage.topics.get_by_project(project_id)
    return {"topics": topics}


@router.get("/{project_id}/topics/{topic_id}")
async def read_topic(topic_id: str,
                     project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Get a specific topic of a project"""
    project_id = project["id"]
    topic = await storage.topics.get(project_id=project_id, topic_id=topic_id)
    if not topic:
        topic_logger.warning(f"topic.read_failed project_id={project_id} topic_id={topic_id} error=topic_not_found")
        raise HTTPException(status_code=404, detail="Topic not found")

    topic_logger.info(f"topic.read project_id={project_id} topic_id={topic_id}")
    return {"topic": topic}


@router.get("/{project_id}/topics")
async def read_topics(project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Get all topics of a project"""
    project_id = project["id"]
    topics = await storage.topics.get_by_project(project_id)
    topic_logger.info(f"topic.list project_id={project_id} count={len(topics)}")
    return {"topics": topics}


@router.patch("/{project_id}/topics/{topic_id}")
async def update_topic(topic_id: int,
                       data: TopicUpdate,
                       project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Update a topic in a project"""
    project_id = project["id"]
    await storage.topics.update(project_id=project_id, topic_id=int(topic_id), data=dict(data))
    topic_logger.info(f"topic.update project_id={project_id} topic_id={topic_id} data={data}")
    topics = await storage.topics.get_by_project(project_id)
    return {"topics": topics}


@router.delete("/{project_id}/topics/{topic_id}")
async def delete_topic(topic_id: int,
                       project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Delete a topic from a project"""
    project_id = project["id"]
    await storage.topics.delete(project_id=project_id, topic_id=int(topic_id))
    topic_logger.info(f"topic.delete project_id={project_id} topic_id={topic_id}")
    topics = await storage.topics.get_by_project(project_id=project_id)
    return {"topics": topics}
