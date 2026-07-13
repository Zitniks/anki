"""Reflection Engine router — Stage 9."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from analytics.reflection import generate
from repositories import storage
from routers.dependencies import get_current_user, get_project_or_404

router = APIRouter(prefix="/api/v1/projects", tags=["reflection"])


@router.get("/{project_id}/reflection")
async def get_reflection(
    project: Annotated[dict, Depends(get_project_or_404)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    """Generate a template-based progress report for this student.

    No LLM — pure data-to-text transformation based on BKT mastery scores,
    accuracy, hint usage, and learning speed.
    """
    project_id = project["id"]
    mastery_records = await storage.topic_mastery.get_by_project(project_id)
    report = generate(mastery_records)

    return {
        "project_id": project_id,
        "generated_at": report.generated_at,
        "summary": report.summary,
        "stats": report.stats,
        "sections": [
            {"title": s.title, "text": s.text}
            for s in report.sections
        ],
    }
