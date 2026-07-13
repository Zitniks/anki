"""SQLAlchemy database models"""

import enum
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Integer,
    ForeignKey,
    Boolean,
    Float,
    create_engine,
    JSON,
    Index,
    UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from settings import settings

# Create base class for models
Base = declarative_base()


class FileEntityType(enum.StrEnum):
    """Entity type for polymorphic file attachments"""

    MESSAGE = "message"
    MATERIAL = "material"
    REPEAT_ITEM = "repeat_item"


class User(Base):
    """Application user (tutor)"""

    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    materials = relationship("Material", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Project(Base):
    """Project (student)"""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    student_name = Column(String(100), nullable=False)
    student_level = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    notes = Column(String(500), nullable=True)

    # Relationships
    user = relationship("User", back_populates="projects")
    chats = relationship("Chat", back_populates="project", cascade="all, delete-orphan")
    vocabulary_items = relationship("Vocabulary", back_populates="project", cascade="all, delete-orphan")
    topic_items = relationship("Topic", back_populates="project", cascade="all, delete-orphan")
    lessons = relationship("Lesson", back_populates="project", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="project", cascade="all, delete-orphan")
    repeat_items = relationship("RepeatItem", back_populates="project", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": str(self.user_id) if self.user_id else None,
            "name": self.name,
            "student_name": self.student_name,
            "student_level": self.student_level,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Chat(Base):
    """Chat within a project"""

    __tablename__ = "chats"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    include_student_description = Column(Boolean, nullable=False, default=True, server_default="true")
    system_prompt_key = Column(String(100), nullable=False, default="default", server_default="default")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "include_student_description": self.include_student_description,
            "system_prompt_key": self.system_prompt_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Message(Base):
    """Message in a chat"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    thinking_blocks = Column(JSON, nullable=True)
    token_count = Column(Integer, default=0)
    is_summarized = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    chat = relationship("Chat", back_populates="messages")
    files = relationship(
        "File",
        primaryjoin="and_(File.entity_type=='message', foreign(File.entity_id)==Message.id)",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="files",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "project_id": self.project_id,
            "role": self.role,
            "content": self.content,
            "thinking_blocks": self.thinking_blocks or [],
            "token_count": self.token_count,
            "is_summarized": self.is_summarized,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class File(Base):
    """Unified file attachments for messages, materials, and repeat items"""

    __tablename__ = "files"
    __table_args__ = (Index("ix_files_entity", "entity_type", "entity_id"), )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(SAEnum(FileEntityType), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False)
    chat_id = Column(String(36), nullable=True, index=True)  # Only for entity_type='message'
    original_filename = Column(String(500), nullable=False)
    stored_filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(50), nullable=False)  # 'image', 'pdf', 'docx', 'audio'
    mime_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    extracted_text = Column(Text, nullable=True)  # Only populated for message files
    meta = Column(JSON, nullable=True)  # Type-specific metadata (e.g. {"width", "height", "source"} for images)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "entity_type": self.entity_type.value if self.entity_type else None,
            "entity_id": self.entity_id,
            "chat_id": self.chat_id,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "extracted_text": self.extracted_text,
            "meta": self.meta,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


class Vocabulary(Base):
    """Vocabulary items for a project"""

    __tablename__ = "vocabulary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    word = Column(String(500), nullable=False)
    extracted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="vocabulary_items")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "word": self.word,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


class Topic(Base):
    """Topics for a project"""

    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    topic = Column(String(500), nullable=False)
    extracted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    level = Column(String(100), nullable=False)
    status = Column(String(100), nullable=False)
    color = Column(String(100), nullable=False)

    # Relationships
    project = relationship("Project", back_populates="topic_items")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "topic": self.topic,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
            "level": self.level,
            "status": self.status,
            "color": self.color,
        }


class Material(Base):
    """Learning materials (exercises, assignments)"""

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(300), nullable=False)
    level = Column(String(100), nullable=True)  # A1, A2, B1, B2, C1, C2
    tags = Column(JSON, nullable=True)  # List of additional tags
    content = Column(Text, nullable=False)  # Exercise text/description
    answers = Column(Text, nullable=True)  # Answers to the exercise
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="materials")
    files = relationship(
        "File",
        primaryjoin="and_(File.entity_type=='material', foreign(File.entity_id)==Material.id)",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="files",
    )
    links = relationship("MaterialLink", back_populates="material", cascade="all, delete-orphan", lazy="selectin")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": str(self.user_id) if self.user_id else None,
            "name": self.name,
            "level": self.level,
            "tags": self.tags if self.tags else [],
            "content": self.content,
            "answers": self.answers,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "files": [f.to_dict() for f in self.files] if self.files else [],
            "links": [link.to_dict() for link in self.links] if self.links else [],
        }


class ExampleBank(Base):
    """Example RAG corpus — grammar usage example sentences."""

    __tablename__ = "example_bank"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sentence = Column(Text, nullable=False)
    topic = Column(String(200), nullable=False)
    level = Column(String(100), nullable=True)  # A1, A2, B1, B2, C1, C2
    translation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": str(self.user_id) if self.user_id else None,
            "sentence": self.sentence,
            "topic": self.topic,
            "level": self.level,
            "translation": self.translation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class KnowledgeDoc(Base):
    """Explanation RAG corpus — source documents (textbooks, articles, notes)."""

    __tablename__ = "knowledge_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(300), nullable=False)
    source = Column(String(500), nullable=True)  # textbook name, URL, ...
    topic = Column(String(200), nullable=True)
    level = Column(String(100), nullable=True)  # A1, A2, B1, B2, C1, C2
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chunks = relationship("KnowledgeChunk", back_populates="doc", cascade="all, delete-orphan", lazy="selectin")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": str(self.user_id) if self.user_id else None,
            "title": self.title,
            "source": self.source,
            "topic": self.topic,
            "level": self.level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "chunk_count": len(self.chunks) if self.chunks else 0,
        }


class KnowledgeChunk(Base):
    """A chunk of a ``KnowledgeDoc``, embedded independently for retrieval."""

    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("knowledge_docs.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    doc = relationship("KnowledgeDoc", back_populates="chunks")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MaterialLink(Base):
    """Link attachments for materials"""

    __tablename__ = "material_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    url = Column(String(2000), nullable=False)
    name = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    material = relationship("Material", back_populates="links")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "material_id": self.material_id,
            "url": self.url,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Lesson(Base):
    """Lessons associated with a project"""

    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="lessons")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "description": self.description,
            "date": self.date.isoformat() if self.date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CalendarEvent(Base):
    """Calendar events (lessons) for scheduling"""

    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    notes = Column(Text, nullable=True)
    color = Column(String(20), nullable=False, default="blue")
    is_recurring = Column(Boolean, default=False, nullable=False)
    recurrence_type = Column(String(20), nullable=True)  # 'weekly', 'biweekly', 'monthly', 'none'
    recurrence_group_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="calendar_events")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "notes": self.notes,
            "color": self.color,
            "is_recurring": self.is_recurring,
            "recurrence_type": self.recurrence_type,
            "recurrence_group_id": self.recurrence_group_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RepeatItem(Base):
    """Repeat items (tests/quizzes/surveys) for a student"""

    __tablename__ = "repeat_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(String(500), nullable=True)
    status = Column(String(20), default="todo", nullable=False)  # 'todo', 'done', etc.
    done_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="repeat_items")
    files = relationship(
        "File",
        primaryjoin="and_(File.entity_type=='repeat_item', foreign(File.entity_id)==RepeatItem.id)",
        cascade="all, delete-orphan",
        lazy="selectin",
        overlaps="files",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "done_at": self.done_at.isoformat() if self.done_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "files": [f.to_dict() for f in self.files] if self.files else [],
        }


class LearningEvent(Base):
    """A single exercise attempt — raw Learning Analytics event."""

    __tablename__ = "learning_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    topic = Column(String(500), nullable=False)
    correct = Column(Boolean, nullable=False)
    time_seconds = Column(Integer, nullable=False)
    attempts = Column(Integer, nullable=False, default=1)
    hint_used = Column(Boolean, nullable=False, default=False)
    confidence = Column(Integer, nullable=True)  # 1–5 self-assessment
    mistakes = Column(JSON, nullable=True)  # list[str]
    difficulty = Column(String(50), nullable=True)  # "easy" | "medium" | "hard"
    exercise_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "topic": self.topic,
            "correct": self.correct,
            "time_seconds": self.time_seconds,
            "attempts": self.attempts,
            "hint_used": self.hint_used,
            "confidence": self.confidence,
            "mistakes": self.mistakes or [],
            "difficulty": self.difficulty,
            "exercise_id": self.exercise_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TopicMastery(Base):
    """Aggregated Student Model per topic — updated after every LearningEvent."""

    __tablename__ = "topic_mastery"
    __table_args__ = (UniqueConstraint("project_id", "topic", name="uq_topic_mastery"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    topic = Column(String(500), nullable=False)
    mastery_score = Column(Float, nullable=False, default=0.5)   # 0.0–1.0, driven by BKT P(know)
    als_score = Column(Float, nullable=False, default=0.0)       # Adaptive Learning Score
    total_attempts = Column(Integer, nullable=False, default=0)
    correct_attempts = Column(Integer, nullable=False, default=0)
    avg_time_seconds = Column(Float, nullable=True)
    hint_usage_rate = Column(Float, nullable=True)               # 0.0–1.0
    last_event_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # BKT parameters
    bkt_p_know = Column(Float, nullable=False, default=0.1)      # P(L) — current P(know)
    bkt_p_transit = Column(Float, nullable=False, default=0.1)   # P(T) — learning rate
    bkt_p_guess = Column(Float, nullable=False, default=0.25)    # P(G) — guess probability
    bkt_p_slip = Column(Float, nullable=False, default=0.1)      # P(S) — slip probability
    bkt_p_correct_next = Column(Float, nullable=True)            # predicted P(correct) next attempt
    is_mastered = Column(Boolean, nullable=False, default=False) # P(know) >= 0.95

    # Confidence Calibration
    avg_confidence = Column(Float, nullable=True)        # rolling avg of student's self-reported confidence
    confidence_bias = Column(Float, nullable=True)       # avg_confidence - accuracy (+ = overconfident)
    calibration_error = Column(Float, nullable=True)     # |confidence_bias| (0 = perfect)

    project = relationship("Project")

    def to_dict(self) -> dict[str, Any]:
        accuracy = round(self.correct_attempts / self.total_attempts, 4) if self.total_attempts else 0.0
        return {
            "id": self.id,
            "project_id": self.project_id,
            "topic": self.topic,
            "mastery_score": self.mastery_score,
            "als_score": self.als_score,
            "total_attempts": self.total_attempts,
            "correct_attempts": self.correct_attempts,
            "accuracy": accuracy,
            "avg_time_seconds": self.avg_time_seconds,
            "hint_usage_rate": self.hint_usage_rate,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "bkt": {
                "p_know": self.bkt_p_know,
                "p_transit": self.bkt_p_transit,
                "p_guess": self.bkt_p_guess,
                "p_slip": self.bkt_p_slip,
                "p_correct_next": self.bkt_p_correct_next,
                "is_mastered": self.is_mastered,
            },
            "calibration": {
                "avg_confidence": self.avg_confidence,
                "confidence_bias": self.confidence_bias,
                "calibration_error": self.calibration_error,
            },
        }


class UsageLog(Base):
    """Token usage record per assistant generation turn."""

    __tablename__ = "usage_log"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chat_id = Column(String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    model_name = Column(String(200), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    reasoning_tokens = Column(Integer, nullable=False, default=0)
    images_generated = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id) if self.id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "project_id": self.project_id,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "model_name": self.model_name,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "images_generated": self.images_generated,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Database connection
def get_database_url(async_mode: bool = False) -> str:
    """Get database connection URL"""
    if async_mode:
        # Async PostgreSQL
        return f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    # Sync PostgreSQL (для миграций)
    return f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


# Async engine
async_engine = create_async_engine(
    get_database_url(async_mode=True),
    # echo=settings.DEBUG,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

# Async session factory
async_session_factory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine (for migrations and table creation)
sync_engine = create_engine(
    get_database_url(async_mode=False),
    # echo=settings.DEBUG,
    echo=False,
)


async def get_db() -> AsyncSession:
    """Dependency to get DB session"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database (create tables)"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Drop all tables (for testing)"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
