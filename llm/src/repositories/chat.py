"""Chat repository"""

from datetime import datetime
from sqlalchemy import select

from database import Chat
from repositories import storage
from repositories.base import BaseRepository
from logger import db_logger


class ChatRepository(BaseRepository[Chat]):
    model = Chat

    async def get_by_project(self, project_id: str) -> list[dict]:
        """All chats for a project, ordered by created_at asc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Chat)
                .where(Chat.project_id == project_id)
                .order_by(Chat.created_at.asc())
            )
            chats = result.scalars().all()
            return [c.to_dict() for c in chats]

    async def update(self, chat_id: str, data: dict) -> dict | None:
        """Update chat fields, returns updated dict or None."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Chat)
                .where(Chat.id == chat_id)
            )
            chat = result.scalar_one_or_none()
            if not chat:
                return None

            for key, value in data.items():
                setattr(chat, key, value)
            chat.updated_at = datetime.utcnow()

            await session.commit()
            return chat.to_dict()

    async def delete(self, chat_id: str) -> bool:
        """Delete chat, its DB records (cascade), and associated files from object storage."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Chat)
                .where(Chat.id == chat_id)
            )
            chat = result.scalar_one_or_none()
            if not chat:
                db_logger.warning(f"db.chat_delete_failed chat_id={chat_id} error=not_found")
                return False

            project_id = chat.project_id

            # Delete files from object storage before cascade deletion removes file records
            try:
                deleted_count = await storage.file_storage.delete_chat_files(chat_id)
                db_logger.info(f"db.chat_files_delete chat_id={chat_id} count={deleted_count}")
            except Exception as e:
                db_logger.error(f"db.chat_files_delete_error chat_id={chat_id} error={e}")

            await session.delete(chat)
            await session.commit()
            db_logger.info(f"db.chat_delete project_id={project_id} chat_id={chat_id}")
            return True
