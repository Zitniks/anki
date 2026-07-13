"""CalendarEvent repository"""

from datetime import datetime
from sqlalchemy import select, and_

from database import CalendarEvent
from repositories.base import BaseRepository
from logger import db_logger


class CalendarEventRepository(BaseRepository[CalendarEvent]):
    model = CalendarEvent

    async def get_filtered(
        self,
        project_id: str | None = None,
        project_ids: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """Get events with optional filters."""
        async with self._session_factory() as session:
            query = select(CalendarEvent)

            filters = []
            if project_id:
                filters.append(CalendarEvent.project_id == project_id)
            elif project_ids is not None:
                filters.append(CalendarEvent.project_id.in_(project_ids))
            if start_date:
                filters.append(CalendarEvent.start_time >= datetime.fromisoformat(start_date))
            if end_date:
                filters.append(CalendarEvent.end_time <= datetime.fromisoformat(end_date))

            if filters:
                query = query.where(and_(*filters))

            result = await session.execute(query)
            events = result.scalars().all()
            return [e.to_dict() for e in events]

    async def update(self, event_id: int, data: dict) -> dict | None:
        """Update event fields."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(CalendarEvent)
                .where(CalendarEvent.id == event_id)
            )
            event = result.scalar_one_or_none()
            if not event:
                return None

            for key, value in data.items():
                setattr(event, key, value)
            event.updated_at = datetime.utcnow()

            await session.commit()
            db_logger.info(f"db.calendar_event_update event_id={event_id}")
            return event.to_dict()

    async def delete_from_group(self, recurrence_group_id: str, from_start_time: datetime) -> int:
        """Delete all events in a recurrence group starting from a given datetime. Returns count deleted."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(CalendarEvent)
                .where(and_(
                    CalendarEvent.recurrence_group_id == recurrence_group_id,
                    CalendarEvent.start_time >= from_start_time,
                ))
            )
            events = result.scalars().all()
            count = len(events)
            for event in events:
                await session.delete(event)
            await session.commit()
            db_logger.info(f"db.calendar_event_delete_from_group group_id={recurrence_group_id} count={count}")
            return count
