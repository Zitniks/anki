"""Project repository"""

from datetime import datetime
from sqlalchemy import func, select

from database import Project
from repositories.base import BaseRepository
from logger import db_logger


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def count_by_user(self, user_id: str) -> int:
        """Count total projects for a user.

        Parameters
        ----------
        user_id : str
            User UUID as string.

        Returns
        -------
        int
            Number of projects owned by this user.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count())
                .where(Project.user_id == user_id)
            )
            return result.scalar_one()

    async def get_all(self, user_id: str) -> list[dict]:
        """Get all projects for a user, ordered by updated_at desc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.updated_at.desc())
            )
            projects = result.scalars().all()
            return [p.to_dict() for p in projects]

    async def update(self, project_id: str, data: dict) -> dict | None:
        """Update project fields, returns updated dict or None."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project)
                .where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                return None

            for key, value in data.items():
                setattr(project, key, value)
            project.updated_at = datetime.utcnow()

            await session.commit()
            return project.to_dict()

    # --- Notes (field on Project) ---

    async def get_notes(self, project_id: str) -> str | None:
        """Get notes for a project."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project)
                .where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            return project.notes if project else None

    async def update_notes(self, project_id: str, notes: str | None) -> None:
        """Update notes for a project. Pass None to delete."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project)
                .where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project:
                project.notes = notes
                await session.commit()
                db_logger.info(f"db.notes_update project_id={project_id}")
