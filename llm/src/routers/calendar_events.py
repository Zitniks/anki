"""Router for calendar events"""

from datetime import datetime
from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Depends

from schemas import CalendarEventCreate
from repositories import storage
from routers.dependencies import get_current_user, verify_project_ownership
from logger import db_logger

router = APIRouter(prefix="/api/v1/calendar-events", tags=["calendar-events"])


@router.post("/")
async def create_calendar_event(event_data: CalendarEventCreate,
                                current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Create a new calendar event"""
    await verify_project_ownership(event_data.project_id, current_user["id"])
    event = await storage.calendar_events.create(data=dict(event_data))
    db_logger.info(f"calendar_event.create event_id={event['id']} project_id={event['project_id']}")
    return {"event": event}


@router.get("/")
async def read_calendar_events(current_user: Annotated[dict, Depends(get_current_user)],
                               project_id: str | None = None,
                               start_date: str | None = None,
                               end_date: str | None = None) -> dict[str, Any]:
    """Get calendar events, optionally filtered by project and date range"""
    if project_id:
        await verify_project_ownership(project_id, current_user["id"])
        events = await storage.calendar_events.get_filtered(project_id=project_id,
                                                            start_date=start_date,
                                                            end_date=end_date)
    else:
        user_projects = await storage.projects.get_all(user_id=current_user["id"])
        project_ids = [p["id"] for p in user_projects]
        events = await storage.calendar_events.get_filtered(project_ids=project_ids,
                                                            start_date=start_date,
                                                            end_date=end_date)
    db_logger.info(f"calendar_event.list project_id={project_id} count={len(events)}")
    return {"events": events}


@router.get("/{event_id}")
async def read_calendar_event(event_id: int,
                              current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get a specific calendar event"""
    event = await storage.calendar_events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    await verify_project_ownership(event["project_id"], current_user["id"])
    db_logger.info(f"calendar_event.read event_id={event_id}")
    return {"event": event}


@router.patch("/{event_id}")
async def update_calendar_event(event_id: int,
                                event_data: CalendarEventCreate,
                                current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Update a calendar event"""
    event = await storage.calendar_events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    await verify_project_ownership(event["project_id"], current_user["id"])
    updated = await storage.calendar_events.update(event_id=event_id, data=dict(event_data))
    db_logger.info(f"calendar_event.update event_id={event_id}")
    return {"event": updated}


@router.delete("/{event_id}")
async def delete_calendar_event(event_id: int,
                                current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete a calendar event"""
    event = await storage.calendar_events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    await verify_project_ownership(event["project_id"], current_user["id"])
    await storage.calendar_events.delete(event_id)
    db_logger.info(f"calendar_event.delete event_id={event_id}")
    return {"status": "deleted"}


@router.delete("/{event_id}/recurring-from")
async def delete_recurring_from(event_id: int,
                                current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete a recurring event and all following events in the same recurrence group"""
    event = await storage.calendar_events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")

    await verify_project_ownership(event["project_id"], current_user["id"])

    if not event.get("recurrence_group_id"):
        raise HTTPException(status_code=400, detail="Event is not part of a recurrence group")

    from_start_time = datetime.fromisoformat(str(event["start_time"]))
    count = await storage.calendar_events.delete_from_group(
        recurrence_group_id=event["recurrence_group_id"],
        from_start_time=from_start_time,
    )
    db_logger.info(f"calendar_event.delete_recurring_from event_id={event_id} count={count}")
    return {"status": "deleted", "count": count}
