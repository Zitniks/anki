"""Recommendation Engine router — Stage 6."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from adaptive.engine import decide
from adaptive.recommendation import difficulty_to_cefr, rank_materials
from repositories import storage
from routers.dependencies import get_current_user, get_project_or_404

router = APIRouter(prefix="/api/v1/projects", tags=["recommendation"])


@router.get("/{project_id}/recommendations")
async def get_recommendations(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
    topic: str | None = None,
    difficulty: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Return a pedagogical decision + matching exercises for this student.

    1. Runs the Adaptive Engine to decide topic & difficulty
       (unless overridden by query params).
    2. Maps difficulty → CEFR levels via student's current level.
    3. Searches the teacher's material library for matching exercises.
    4. Excludes exercises already attempted; ranks by relevance.

    Query params
    ------------
    topic : str, optional
        Override the engine's topic choice.
    difficulty : str, optional
        Override the engine's difficulty choice (easy | medium | hard).
    limit : int, optional
        Max exercises to return (default 5).
    """
    project_id = project["id"]
    user_id = current_user["id"]

    # ── Step 1: Adaptive decision ──────────────────────────────────────────
    mastery_records = await storage.topic_mastery.get_by_project(project_id)
    decision = decide(mastery_records, current_topic=topic)

    # Allow caller to override difficulty
    effective_difficulty = difficulty or decision.difficulty
    effective_topic = topic or decision.topic

    # ── Step 2: Map difficulty → CEFR ─────────────────────────────────────
    student_level = project.get("student_level", "B1")
    cefr_levels = difficulty_to_cefr(student_level, effective_difficulty)

    # ── Step 3: Fetch + filter materials ──────────────────────────────────
    materials = await storage.materials.search(
        user_id=user_id,
        topic=effective_topic,
        levels=cefr_levels,
    )

    # ── Step 4: Exclude seen, rank, limit ─────────────────────────────────
    events = await storage.learning_events.get_by_project(project_id, limit=200)
    seen_ids = {e["exercise_id"] for e in events if e.get("exercise_id")}

    ranked = rank_materials(materials, effective_topic, cefr_levels, seen_ids)[:limit]

    return {
        "project_id": project_id,
        "decision": {
            "action": decision.action,
            "topic": effective_topic,
            "difficulty": effective_difficulty,
            "reason": decision.reason,
            "mastery_score": decision.mastery_score,
            "als_score": decision.als_score,
        },
        "cefr_levels": cefr_levels,
        "exercises": ranked,
        "total_found": len(materials),
    }
