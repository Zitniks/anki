"""Usage telemetry router: per-user token + image consumption."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from repositories import storage
from routers.dependencies import get_current_user
from settings import settings

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])


@router.get("/me")
async def get_my_usage(
    current_user: Annotated[dict, Depends(get_current_user)],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> dict[str, Any]:
    """Return the current user's usage summary plus today's totals and limits."""
    user_id = current_user["id"]
    summary = await storage.usage_log.get_window_summary(user_id, days)
    tokens_today = await storage.usage_log.get_daily_tokens(user_id)
    images_today = await storage.usage_log.get_daily_images(user_id)

    return {
        "today": {"tokens": tokens_today, "images": images_today},
        "limits": {
            "daily_tokens": settings.DAILY_TOKEN_LIMIT,
            "daily_images": settings.DAILY_IMAGE_LIMIT,
        },
        "window_days": days,
        **summary,
    }
