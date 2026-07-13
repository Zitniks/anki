"""Adaptive Engine router — Stage 5."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from adaptive.engine import decide
from repositories import storage
from routers.dependencies import get_project_or_404

router = APIRouter(prefix="/api/v1/projects", tags=["adaptive"])


@router.get("/{project_id}/adaptive/next")
async def get_next_action(
    project: Annotated[dict, Depends(get_project_or_404)],
    topic: str | None = None,
) -> dict[str, Any]:
    """Return the next pedagogical decision for this student.

    Pass ``?topic=Present+Perfect`` to evaluate a specific topic,
    or omit it to let the engine pick the weakest one automatically.
    """
    project_id = project["id"]
    mastery_records = await storage.topic_mastery.get_by_project(project_id)
    decision = decide(mastery_records, current_topic=topic)
    return {
        "project_id": project_id,
        "decision": {
            "action": decision.action,
            "topic": decision.topic,
            "difficulty": decision.difficulty,
            "reason": decision.reason,
            "mastery_score": decision.mastery_score,
            "als_score": decision.als_score,
            "calibration": decision.calibration,
        },
    }
