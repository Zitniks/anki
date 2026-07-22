"""Material repository"""

from datetime import datetime
from sqlalchemy import select, or_, cast, String

from database import Material
from repositories.base import BaseRepository
from logger import db_logger


class MaterialRepository(BaseRepository[Material]):
    model = Material

    async def get_all(self, user_id: str) -> list[dict]:
        """Get all materials for a user."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Material)
                .where(Material.user_id == user_id)
                .order_by(Material.created_at.desc())
            )
            materials = result.scalars().all()
            return [m.to_dict() for m in materials]

    async def search(
        self,
        user_id: str,
        topic: str | None = None,
        levels: list[str] | None = None,
    ) -> list[dict]:
        """Search materials by topic and/or CEFR levels.

        Parameters
        ----------
        user_id : str
            Owner of the materials.
        topic : str or None
            Topic keyword searched in tags (JSON) and name.
        levels : list[str] or None
            Acceptable CEFR levels (e.g. ["B1", "A2", "B2"]).
            If None, no level filter is applied.

        Returns
        -------
        list[dict]
            Matching material dicts, newest first.
        """
        async with self._session_factory() as session:
            q = select(Material).where(Material.user_id == user_id)

            if topic:
                # Cast JSON tags to text for a case-insensitive substring match.
                # Also search the name field. Both cover the common tagging style.
                q = q.where(
                    or_(
                        cast(Material.tags, String).ilike(f"%{topic}%"),
                        Material.name.ilike(f"%{topic}%"),
                    )
                )

            if levels:
                q = q.where(Material.level.in_(levels))

            q = q.order_by(Material.created_at.desc())
            result = await session.execute(q)
            return [m.to_dict() for m in result.scalars().all()]

    async def update(self, material_id: int, data: dict) -> dict | None:
        """Update material fields, returns updated dict or None."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Material)
                .where(Material.id == material_id)
            )
            material = result.scalar_one_or_none()
            if not material:
                return None

            for key, value in data.items():
                setattr(material, key, value)
            material.updated_at = datetime.utcnow()

            await session.commit()
            db_logger.info(f"db.material_update material_id={material_id}")
            return material.to_dict()
