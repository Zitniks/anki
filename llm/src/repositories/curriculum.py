"""Репозиторий пройденных уроков."""

from datetime import datetime

from sqlalchemy import select

from database import Lesson
from logger import db_logger
from repositories.base import BaseRepository


class LessonRepository(BaseRepository[Lesson]):
    model = Lesson

    async def get_by_project(self, project_id: str) -> list[dict]:
        """All lessons for a project."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Lesson)
                .where(Lesson.project_id == project_id)
            )
            lessons = result.scalars().all()
            return [lesson.to_dict() for lesson in lessons]

    async def update(self, lesson_id: int, data: dict) -> dict | None:
        """Update lesson fields."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Lesson)
                .where(Lesson.id == lesson_id)
            )
            lesson = result.scalar_one_or_none()
            if not lesson:
                return None

            for key, value in data.items():
                setattr(lesson, key, value)
            lesson.updated_at = datetime.utcnow()

            await session.commit()
            db_logger.info(f"db.lesson_update lesson_id={lesson_id}")
            return lesson.to_dict()
