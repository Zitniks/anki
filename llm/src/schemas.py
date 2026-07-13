"""Pydantic schemas for API"""

from enum import StrEnum
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime


class AttachmentType(StrEnum):
    """Type of attachment"""

    IMAGE = "image"
    PDF = "pdf"
    DOCX = "docx"
    AUDIO = "audio"


class FileAttachment(BaseModel):
    """Attachment data (images, PDFs, DOCX, audio files)"""

    dataUrl: str  # noqa: N815
    name: str
    type: AttachmentType | None = None  # Optional for backward compatibility


class ProjectCreate(BaseModel):
    """Схема создания проекта"""

    name: str = Field(..., min_length=1, max_length=200, description="Название проекта")
    student_name: str = Field(..., min_length=1, max_length=100, description="Имя студента")
    student_level: str = Field(..., min_length=1, max_length=100, description="Уровень студента")
    description: str | None = Field(None, max_length=1000, description="Описание проекта")
    notes: str | None = Field(None, max_length=500, description="Заметки о студенте")


class ChatCreate(BaseModel):
    """Схема создания/обновления чата"""

    name: str = Field(..., min_length=1, max_length=200, description="Название чата")


class ChatRequest(BaseModel):
    """Схема запроса в чат"""

    message: str = Field(default="", max_length=5000, description="Сообщение пользователя")
    attachments: list[FileAttachment] | None = []


class VocabularyUpdate(BaseModel):
    """Схема обновления лексики"""

    items: list[str] = Field(..., min_items=1, description="Список слов/фраз для добавления")


class TopicUpdate(BaseModel):
    topic: str = Field(..., description="Название темы для обновления")
    level: str = Field(..., description="Уровень темы")
    status: str = Field(..., description="Статус темы для обновления (пройдена, повторить, знает, не пройдена)")
    color: str = Field(..., description="Цвет темы для обновления (в зависимости от статуса)")


class NotesUpdate(BaseModel):
    notes: str = Field(..., description="Заметки о студенте")


class MaterialLinkData(BaseModel):
    url: str = Field(..., description="URL ссылки")
    name: str = Field(..., description="Название ссылки")


class MaterialData(BaseModel):
    name: str = Field(..., description="Название материала")
    level: str = Field(..., description="Уровень материала")
    tags: list[str] = Field(default=[], description="Теги для материала")
    content: str = Field(..., description="Содержание задания")
    answers: str | None = Field(..., description="Ответы на задание")


class ExampleData(BaseModel):
    sentence: str = Field(..., description="Предложение-пример")
    topic: str = Field(..., description="Грамматическая тема")
    level: str | None = Field(default=None, description="Уровень CEFR")
    translation: str | None = Field(default=None, description="Перевод предложения")


class KnowledgeDocData(BaseModel):
    title: str = Field(..., description="Название документа")
    content: str = Field(..., description="Полный текст документа (будет разбит на чанки)")
    source: str | None = Field(default=None, description="Источник (учебник, URL)")
    topic: str | None = Field(default=None, description="Грамматическая тема")
    level: str | None = Field(default=None, description="Уровень CEFR")


class MessageResponse(BaseModel):
    """Схема ответа сообщения"""

    role: str
    content: str
    timestamp: datetime


class ChatResponse(BaseModel):
    """Схема ответа чата"""

    id: str
    project_id: str
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectResponse(BaseModel):
    """Схема ответа проекта"""

    id: str
    name: str
    student_name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class StreamResponse(BaseModel):
    """Схема ответа чата"""

    message: MessageResponse
    was_summarized: bool = False
    extracted_vocabulary: list[str] = []
    extracted_topics: list[str] = []


class LessonCreate(BaseModel):
    """Схема создания урока"""

    project_id: str = Field(..., description="ID проекта")
    description: str = Field(..., description="Описание урока")
    date: datetime = Field(..., description="Дата урока")


class RepeatItemCreate(BaseModel):
    """Schema for creating a repeat item"""

    title: str = Field(..., min_length=1, max_length=300, description="Item title")
    description: str | None = Field(None, max_length=500, description="Item description")


class RepeatItemUpdate(BaseModel):
    """Schema for updating a repeat item"""

    title: str | None = None
    description: str | None = None
    status: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105


class UserResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime


class LearningEventCreate(BaseModel):
    """Schema for logging a single exercise attempt."""

    topic: str = Field(..., description="Topic name, e.g. 'Present Perfect'")
    correct: bool = Field(..., description="Whether the answer was correct")
    time_seconds: int = Field(..., ge=0, description="Time spent in seconds")
    attempts: int = Field(1, ge=1, description="Number of attempts")
    hint_used: bool = Field(False, description="Whether a hint was used")
    confidence: int | None = Field(None, ge=1, le=5, description="Self-assessed confidence 1–5")
    mistakes: list[str] | None = Field(None, description="List of mistake type labels")
    difficulty: str | None = Field(None, description="'easy' | 'medium' | 'hard'")
    exercise_id: int | None = Field(None, description="Optional reference to a material/exercise")


class CalendarEventCreate(BaseModel):
    """Схема создания календарного события"""

    project_id: str = Field(..., description="ID проекта (студента)")
    start_time: datetime = Field(..., description="Начало события")
    end_time: datetime = Field(..., description="Конец события")
    notes: str | None = Field(None, description="Заметки о занятии")
    color: str = Field("blue", description="Цвет события (blue/green/pink)")
    is_recurring: bool = Field(False, description="Является ли событие повторяющимся")
    recurrence_type: str | None = Field(None, description="Тип повторения (weekly/biweekly/monthly/none)")
    recurrence_group_id: str | None = Field(None, description="ID группы повторяющихся событий")


class FileResponse(BaseModel):
    """Schema for file attachment responses"""

    id: UUID
    entity_type: str
    entity_id: int
    original_filename: str
    file_type: str
    mime_type: str
    file_size: int
    uploaded_at: datetime
    extracted_text: str | None = None


# ========== DOMAIN MODELS ==========


class ProjectContext(BaseModel):
    """Project context for LLM prompt building."""

    student_name: str
    student_level: str
    description: str
    existing_vocabulary: list[str] = Field(default_factory=list)
    existing_topics: list[str] = Field(default_factory=list)


class ChatSettingsUpdate(BaseModel):
    """Request body for updating per-chat settings."""

    include_student_description: bool
    system_prompt_key: str = "default"


# ========== STREAMING EVENTS ==========


class ContentEvent(BaseModel):
    type: Literal["content"] = "content"
    content: str


class ThinkingStartEvent(BaseModel):
    type: Literal["thinking_start"] = "thinking_start"


class ThinkingEvent(BaseModel):
    type: Literal["thinking"] = "thinking"
    content: str


class ThinkingDoneEvent(BaseModel):
    type: Literal["thinking_done"] = "thinking_done"


class ThoughtWrapEvent(BaseModel):
    type: Literal["thought_wrap"] = "thought_wrap"


class StatusEvent(BaseModel):
    type: Literal["status"] = "status"
    status: str


class WarningEvent(BaseModel):
    type: Literal["warning"] = "warning"
    warning: str


class ImagesEvent(BaseModel):
    """Batched image event: one per tool call, carrying all images from that call.

    Each ``images[i]`` dict carries at minimum ``url`` and ``name``; ``width``,
    ``height``, ``source`` are present when known (Pexels always, generated /
    user uploads after PIL probe).
    """
    type: Literal["images"] = "images"
    images: list[dict]


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"


ChatStreamEvent = (ContentEvent
                   | ThinkingStartEvent
                   | ThinkingEvent
                   | ThinkingDoneEvent
                   | ThoughtWrapEvent
                   | StatusEvent
                   | WarningEvent
                   | ImagesEvent
                   | ErrorEvent
                   | DoneEvent)
