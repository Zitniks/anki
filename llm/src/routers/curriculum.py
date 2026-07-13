"""Curriculum Planner router — Stage 7."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from adaptive.curriculum import build_plan
from repositories import storage
from routers.dependencies import get_current_user, get_project_or_404

router = APIRouter(prefix="/api/v1/projects", tags=["curriculum"])


@router.get("/{project_id}/curriculum")
async def get_curriculum(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
    lessons: int = Query(default=5, ge=1, le=20),
    topics_per_lesson: int = Query(default=2, ge=1, le=5),
) -> dict[str, Any]:
    """Generate a personalised study plan for this student.

    Uses topological sort of the prerequisite graph + ZPD classification
    to decide which topics to teach and in what order.

    Query params
    ------------
    lessons : int
        Number of lessons to plan ahead (1–20, default 5).
    topics_per_lesson : int
        Topics per lesson (1–5, default 2).
    """
    project_id = project["id"]
    mastery_records = await storage.topic_mastery.get_by_project(project_id)
    plan = build_plan(mastery_records, num_lessons=lessons, topics_per_lesson=topics_per_lesson)

    return {
        "project_id": project_id,
        "summary": plan.summary,
        "lessons": [
            {
                "lesson": lesson.lesson_number,
                "topics": [
                    {
                        "topic": s.topic,
                        "zone": s.zone,
                        "p_know": s.p_know,
                        "prerequisites": s.prerequisites,
                        "blocking": s.blocking,
                    }
                    for s in lesson.topics
                ],
            }
            for lesson in plan.lessons
        ],
        "mastered": plan.mastered,
        "blocked": [
            {
                "topic": s.topic,
                "p_know": s.p_know,
                "blocking": s.blocking,
            }
            for s in plan.blocked
        ],
    }
