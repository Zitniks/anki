"""Router registry.

Single source of truth for which routers the FastAPI app exposes.
``main.py`` iterates ``ALL_ROUTERS`` and calls ``app.include_router`` on each.
Add a new router by appending it here.
"""

from routers.adaptive import router as adaptive_router
from routers.curriculum import router as curriculum_router
from routers.recommendation import router as recommendation_router
from routers.analytics import router as analytics_router
from routers.reflection import router as reflection_router
from routers.rag import router as rag_router
from routers.auth import router as auth_router
from routers.calendar_events import router as calendar_events_router
from routers.chat import router as chat_router
from routers.example_bank import router as example_bank_router
from routers.files import router as files_router
from routers.knowledge_docs import router as knowledge_docs_router
from routers.lessons import router as lessons_router
from routers.materials import router as materials_router
from routers.notes import router as notes_router
from routers.pages import router as pages_router
from routers.project import router as project_router
from routers.repeat_items import router as repeat_items_router
from routers.topics import router as topics_router
from routers.usage import router as usage_router
from routers.vocabulary import router as vocabulary_router

ALL_ROUTERS = [
    auth_router,
    pages_router,
    chat_router,
    project_router,
    topics_router,
    vocabulary_router,
    notes_router,
    materials_router,
    example_bank_router,
    knowledge_docs_router,
    lessons_router,
    calendar_events_router,
    files_router,
    repeat_items_router,
    usage_router,
    analytics_router,
    adaptive_router,
    recommendation_router,
    curriculum_router,
    reflection_router,
    rag_router,
]
