"""Base repository with common CRUD operations"""

from typing import TypeVar, Generic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):  # noqa: UP046
    """Base repository. Each method creates a session, commits, and closes.
    Accepts/returns dicts. ORM models are internal only."""

    model: type[T]

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def get(self, id: int | str) -> dict | None:  # noqa: A002
        """Get entity by primary key. Returns dict or None."""
        async with self._session_factory() as session:
            result = await session.execute(select(self.model).where(self.model.id == id))
            entity = result.scalar_one_or_none()
            return entity.to_dict() if entity else None

    async def get_all(self) -> list[dict]:
        """Get all entities."""
        async with self._session_factory() as session:
            result = await session.execute(select(self.model))
            entities = result.scalars().all()
            return [e.to_dict() for e in entities]

    async def create(self, data: dict) -> dict:
        """Create entity from dict. Returns created entity as dict."""
        async with self._session_factory() as session:
            entity = self.model(**data)
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity.to_dict()

    async def create_many(self, items: list[dict]) -> list[dict]:
        """Batch create. Returns list of created dicts."""
        async with self._session_factory() as session:
            entities = [self.model(**item) for item in items]
            session.add_all(entities)
            await session.commit()
            return [e.to_dict() for e in entities]

    async def delete(self, id: int | str) -> bool:  # noqa: A002
        """Delete by id. Returns True if found and deleted."""
        async with self._session_factory() as session:
            result = await session.execute(select(self.model).where(self.model.id == id))
            entity = result.scalar_one_or_none()
            if not entity:
                return False
            await session.delete(entity)
            await session.commit()
            return True
