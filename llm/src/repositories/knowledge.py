"""Knowledge document repository"""

from sqlalchemy import select

from database import KnowledgeDoc
from repositories.base import BaseRepository


class KnowledgeDocRepository(BaseRepository[KnowledgeDoc]):
    model = KnowledgeDoc

    async def get_all(self, user_id: str) -> list[dict]:
        """Get all knowledge documents for a user."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(KnowledgeDoc)
                .where(KnowledgeDoc.user_id == user_id)
                .order_by(KnowledgeDoc.created_at.desc())
            )
            docs = result.scalars().all()
            return [d.to_dict() for d in docs]
