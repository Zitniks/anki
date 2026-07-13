"""Topic repository"""

from sqlalchemy import select, and_

from database import Topic
from repositories.base import BaseRepository
from logger import db_logger


class TopicRepository(BaseRepository[Topic]):
    model = Topic

    async def get_by_project(self, project_id: str) -> list[dict]:
        """All topics for a project, ordered by extracted_at asc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Topic)
                .where(Topic.project_id == project_id)
                .order_by(Topic.extracted_at.asc())
            )
            items = result.scalars().all()
            return [item.to_dict() for item in items]

    async def get(self, project_id: str, topic_id: int) -> dict | None:
        """Single topic by project + topic id."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Topic)
                .where(and_(Topic.project_id == project_id, Topic.id == topic_id))
            )
            item = result.scalar_one_or_none()
            return item.to_dict() if item else None

    async def create(self, project_id: str, data: dict) -> dict | None:
        """Create topic if not duplicate (topic, level). Returns None if duplicate."""
        topic_data = {"project_id": project_id, **data}
        topic_item = Topic(**topic_data)

        async with self._session_factory() as session:
            result = await session.execute(
                select(Topic.topic, Topic.level)
                .where(Topic.project_id == project_id)
            )
            existing_data = [(row[0], row[1]) for row in result.all()]

            if (topic_item.topic, topic_item.level) not in existing_data:
                session.add(topic_item)
                await session.commit()
                db_logger.info(
                    f"db.topic_create project_id={project_id} topic={topic_item.topic} status={topic_item.status}")
                return topic_item.to_dict()
            return None

    async def create_many(self, project_id: str, topics_data: list[dict]) -> list[dict]:
        """Batch create, skipping duplicates by topic name."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Topic.topic)
                .where(Topic.project_id == project_id)
            )
            existing_data = [row[0] for row in result.all()]

            new_items = []
            for topic_data in topics_data:
                topic_item = Topic(**topic_data)
                if topic_item.topic not in existing_data:
                    new_items.append(topic_item)

            if new_items:
                session.add_all(new_items)
                await session.commit()
                db_logger.info(f"db.topics_create project_id={project_id} count={len(new_items)}")

            return [item.to_dict() for item in new_items]

    async def update(self, project_id: str, topic_id: int, data: dict) -> dict | None:
        """Update topic fields."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Topic)
                .where(and_(Topic.project_id == project_id, Topic.id == topic_id))
            )
            topic = result.scalar_one_or_none()
            if not topic:
                return None

            for key, value in data.items():
                setattr(topic, key, value)

            await session.commit()
            db_logger.info(f"db.topic_update project_id={project_id} topic_id={topic_id} data={data}")
            return topic.to_dict()

    async def delete(self, project_id: str, topic_id: int) -> bool:
        """Delete topic. Returns False if not found."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Topic)
                .where(and_(Topic.project_id == project_id, Topic.id == topic_id))
            )
            topic = result.scalar_one_or_none()
            if not topic:
                return False

            await session.delete(topic)
            await session.commit()
            db_logger.info(f"db.topic_delete project_id={project_id} topic_id={topic_id}")
            return True
