"""Chat request lifecycle: save user message → load context → stream → persist."""

from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from langgraph.graph.state import CompiledStateGraph

from chat.persistence import (
    load_context,
    save_user_message,
)
from chat.state import TutorRuntimeContext
from chat.streaming import stream_chat_response
from logger import chat_logger
from repositories import storage
from schemas import ChatRequest
from settings import settings

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def handle_chat(
    chat_id: str,
    project_id: str,
    user_id: str,
    request: ChatRequest,
    graph: CompiledStateGraph,
) -> StreamingResponse:
    """Handle a single chat request."""
    chat_logger.info(f"chat.request project_id={project_id} chat_id={chat_id} "
                     f"has_attachments={len(request.attachments) if request.attachments else 0}")

    saved = await save_user_message(
        chat_id=chat_id,
        project_id=project_id,
        content=request.message,
        attachments=request.attachments,
    )
    loaded = await load_context(chat_id=chat_id, project_id=project_id)

    token_warning = False
    if settings.DAILY_TOKEN_LIMIT > 0:
        tokens_today = await storage.usage_log.get_daily_tokens(user_id)
        if tokens_today >= settings.DAILY_TOKEN_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Daily token limit reached. Try again tomorrow.",
            )
        token_warning = tokens_today / settings.DAILY_TOKEN_LIMIT > 0.85

    runtime_context = TutorRuntimeContext(
        chat_id=chat_id,
        project_id=project_id,
        user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
        history=loaded.history,
        documents_context=loaded.documents_context,
        system_prompt_key=loaded.system_prompt_key,
        include_student_description=loaded.include_student_description,
        project=loaded.project,
        current_user_message=_build_user_message(saved.user_query, saved.user_images),
    )

    return StreamingResponse(
        stream_chat_response(
            graph=graph,
            runtime_context=runtime_context,
            message_id=saved.message_id,
            has_large_document=saved.has_large_document,
            token_warning=token_warning,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def get_graph(request: Request) -> CompiledStateGraph:
    """FastAPI dependency that returns the compiled graph from app state."""
    return request.app.state.graph


def _build_user_message(user_query: str, user_images: list[dict]) -> HumanMessage:
    """Build the current-turn user message, optionally with inline images."""
    if user_images:
        content = [{"type": "text", "text": user_query}]
        for img in user_images:
            content.append({"type": "image_url", "image_url": {"url": img["url"]}})
        return HumanMessage(content=content)
    return HumanMessage(content=user_query)
