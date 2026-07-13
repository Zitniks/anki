"""Storage manager — provides access to all repositories."""

from typing import Any, ClassVar

from database import async_session_factory

from repositories.calendar_event import CalendarEventRepository
from repositories.chat import ChatRepository
from repositories.curriculum import LessonRepository, RepeatItemRepository
from repositories.example import ExampleRepository
from repositories.file import FileRepository
from repositories.file_storage import FileStorageRepository
from repositories.knowledge import KnowledgeDocRepository
from repositories.learning_event import LearningEventRepository
from repositories.material import MaterialLinkRepository, MaterialRepository
from repositories.message import MessageRepository
from repositories.project import ProjectRepository
from repositories.topic import TopicRepository
from repositories.topic_mastery import TopicMasteryRepository
from repositories.usage_log import UsageLogRepository
from repositories.user import UserRepository
from repositories.vocabulary import VocabularyRepository


class Storage:
    """Lazy repository accessor.

    Each ``storage.<name>`` access builds a fresh repository instance
    (cheap — repos hold only a session factory). Add a new repository
    by appending to ``REPOSITORIES``.
    """

    REPOSITORIES: ClassVar[dict[str, type]] = {
        "projects": ProjectRepository,
        "chats": ChatRepository,
        "messages": MessageRepository,
        "files": FileRepository,
        "file_storage": FileStorageRepository,
        "vocabulary": VocabularyRepository,
        "topics": TopicRepository,
        "materials": MaterialRepository,
        "material_links": MaterialLinkRepository,
        "lessons": LessonRepository,
        "calendar_events": CalendarEventRepository,
        "repeat_items": RepeatItemRepository,
        "users": UserRepository,
        "usage_log": UsageLogRepository,
        "learning_events": LearningEventRepository,
        "topic_mastery": TopicMasteryRepository,
        "example_bank": ExampleRepository,
        "knowledge_docs": KnowledgeDocRepository,
    }

    def __init__(self) -> None:
        self._session_factory = async_session_factory

    def __getattr__(self, name: str) -> Any:
        cls = type(self).REPOSITORIES.get(name)
        if cls is None:
            raise AttributeError(f"Storage has no repository {name!r}")
        return cls(self._session_factory)


storage = Storage()
