"""Unified file repository"""

from sqlalchemy import select

from database import Chat, File, FileEntityType, Project
from repositories.base import BaseRepository


class FileRepository(BaseRepository[File]):
    model = File

    async def get_by_entity(self, entity_type: FileEntityType, entity_id: int) -> list[dict]:
        """Files for any entity, ordered by uploaded_at asc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(File)
                .where(File.entity_type == entity_type,
                       File.entity_id == entity_id)
                .order_by(File.uploaded_at.asc())
            )
            files = result.scalars().all()
            return [f.to_dict() for f in files]

    async def get_by_chat(self, chat_id: str) -> list[dict]:
        """Message files for a chat, ordered by uploaded_at asc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(File)
                .where(File.chat_id == chat_id)
                .order_by(File.uploaded_at.asc())
            )
            files = result.scalars().all()
            return [f.to_dict() for f in files]

    async def get_all_with_context(self, user_id: str) -> list[dict]:
        """All message files for a user's projects, joined with chat and project info."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(File,
                       Chat.name.label("chat_name"),
                       Project.id.label("project_id"),
                       Project.student_name)
                .join(Chat, File.chat_id == Chat.id)
                .join(Project, Chat.project_id == Project.id)
                .where(File.entity_type == FileEntityType.MESSAGE,
                       Project.user_id == user_id)
                .order_by(File.uploaded_at.desc()))
            rows = result.all()
            files = []
            for f, chat_name, project_id, student_name in rows:
                d = f.to_dict()
                d["chat_name"] = chat_name
                d["project_id"] = project_id
                d["student_name"] = student_name
                files.append(d)
            return files
