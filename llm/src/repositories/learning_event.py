"""Repository for LearningEvent."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from database import LearningEvent
from repositories.base import BaseRepository


class LearningEventRepository(BaseRepository[LearningEvent]):
    """CRUD + project-scoped queries for LearningEvent."""

    model = LearningEvent

    async def get_by_project(self, project_id: str, limit: int = 100) -> list[dict]:
        """Return learning events for a project, newest first.

        Parameters
        ----------
        project_id : str
            Project UUID string.
        limit : int, optional
            Maximum number of events to return (default 100).

        Returns
        -------
        list[dict]
            Serialised LearningEvent dicts.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(LearningEvent)
                .where(LearningEvent.project_id == project_id)
                .order_by(LearningEvent.created_at.desc())
                .limit(limit)
            )
            return [e.to_dict() for e in result.scalars().all()]

    async def get_by_topic(self, project_id: str, topic: str) -> list[dict]:
        """Return all events for a specific topic, newest first.

        Parameters
        ----------
        project_id : str
            Project UUID string.
        topic : str
            Topic name.

        Returns
        -------
        list[dict]
            Serialised LearningEvent dicts.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(LearningEvent)
                .where(
                    LearningEvent.project_id == project_id,
                    LearningEvent.topic == topic,
                )
                .order_by(LearningEvent.created_at.desc())
            )
            return [e.to_dict() for e in result.scalars().all()]
