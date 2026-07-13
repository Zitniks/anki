"""Example bank repository"""

from sqlalchemy import select

from database import ExampleBank
from repositories.base import BaseRepository


class ExampleRepository(BaseRepository[ExampleBank]):
    model = ExampleBank

    async def get_all(self, user_id: str) -> list[dict]:
        """Get all example sentences for a user."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ExampleBank)
                .where(ExampleBank.user_id == user_id)
                .order_by(ExampleBank.created_at.desc())
            )
            examples = result.scalars().all()
            return [e.to_dict() for e in examples]
