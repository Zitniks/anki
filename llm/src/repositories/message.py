"""Message repository"""

from sqlalchemy import select, and_

from database import Message
from repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def get_by_chat(self, chat_id: str) -> list[dict]:
        """All messages for a chat, ordered by id asc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.id.asc())
            )
            messages = result.scalars().all()
            return [m.to_dict() for m in messages]

    async def get(self, chat_id: str, message_id: int) -> dict | None:
        """Single message by chat + message id."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Message)
                .where(and_(Message.chat_id == chat_id, Message.id == message_id))
            )
            message = result.scalar_one_or_none()
            return message.to_dict() if message else None

    async def get_count(self, chat_id: str) -> int:
        """Message count in a chat."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
            )
            return len(result.scalars().all())
