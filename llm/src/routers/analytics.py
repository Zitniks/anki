"""Learning Analytics router — Stage 2 / 3 / 4."""

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from schemas import LearningEventCreate
from repositories import storage
from routers.dependencies import get_project_or_404

router = APIRouter(prefix="/api/v1/projects", tags=["analytics"])


@router.post("/{project_id}/analytics/events")
async def log_learning_event(
    data: LearningEventCreate,
    project: Annotated[dict, Depends(get_project_or_404)],
) -> dict[str, Any]:
    """Log one exercise attempt, then update the Student Model for that topic."""
    project_id = project["id"]
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    event = await storage.learning_events.create({
        "project_id": project_id,
        "topic": data.topic,
        "correct": data.correct,
        "time_seconds": data.time_seconds,
        "attempts": data.attempts,
        "hint_used": data.hint_used,
        "confidence": data.confidence,
        "mistakes": data.mistakes,
        "difficulty": data.difficulty,
        "exercise_id": data.exercise_id,
        "created_at": now,
    })

    mastery = await storage.topic_mastery.update_from_event(
        project_id=project_id,
        topic=data.topic,
        correct=data.correct,
        time_seconds=data.time_seconds,
        attempts=data.attempts,
        hint_used=data.hint_used,
        confidence=data.confidence,
        event_at=now,
    )

    return {"event": event, "topic_mastery": mastery}


@router.get("/{project_id}/analytics/student-model")
async def get_student_model(
    project: Annotated[dict, Depends(get_project_or_404)],
) -> dict[str, Any]:
    """Return the full Student Model: mastery and ALS for every topic seen."""
    project_id = project["id"]
    topics = await storage.topic_mastery.get_by_project(project_id)
    return {"project_id": project_id, "student_model": topics}


@router.get("/{project_id}/analytics/events")
async def get_learning_events(
    project: Annotated[dict, Depends(get_project_or_404)],
    limit: int = 100,
) -> dict[str, Any]:
    """Return recent learning events for a project, newest first."""
    project_id = project["id"]
    events = await storage.learning_events.get_by_project(project_id, limit=limit)
    return {"project_id": project_id, "events": events}
