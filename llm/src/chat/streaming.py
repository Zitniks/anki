"""Streaming layer for the tutor chat: LangGraph event normalization + SSE generation.

Owns three concerns that previously lived split across ``graph.py`` and
``lifecycle.py``:

1. The LangGraph ``astream_events`` consumer loop with retry, thinking-block
   state machine, and token accounting.
2. Normalization of raw LangGraph events into typed :class:`ChatStreamEvent`
   instances.
3. The outer SSE generator used by FastAPI (warnings + agent events +
   persistence + done frame).
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator

from langgraph.graph.state import CompiledStateGraph

from chat.persistence import save_assistant_message
from chat.state import TutorRuntimeContext, build_runnable_config
from logger import chat_logger, llm_logger
from repositories import storage
from schemas import (
    ChatStreamEvent,
    ContentEvent,
    DoneEvent,
    ErrorEvent,
    ImagesEvent,
    StatusEvent,
    ThinkingDoneEvent,
    ThinkingEvent,
    ThinkingStartEvent,
    ThoughtWrapEvent,
    WarningEvent,
)
from settings import settings

TOOL_STATUS_MAP = {
    "process_youtube_link": "Загружаю транскрипт видео",
    "generate_image": "Генерирую изображение",
    "search_stock_photos": "Ищу фото",
    "extract_vocabulary": "Извлекаю лексику",
    "get_recent_lessons": "Загружаю историю уроков",
    "get_vocabulary": "Загружаю словарный запас",
    "list_materials": "Загружаю список материалов",
    "get_material_by_id": "Открываю материал",
    "save_material": "Сохраняю материал",
}

_IMAGE_TOOL_NAMES = {"generate_image", "search_stock_photos"}


def format_sse(event: ChatStreamEvent) -> str:
    """Format a typed event as an SSE ``data:`` frame."""
    return f"data: {event.model_dump_json()}\n\n"


class ThinkingState:
    """Reasoning-block accumulator for one agent run.

    The agent emits reasoning chunks separately from content; we accumulate
    them into discrete blocks and tell the caller when to emit
    :class:`ThinkingStartEvent` / :class:`ThinkingDoneEvent`.
    """

    def __init__(self) -> None:
        self.blocks: list[str] = []
        self._current = ""
        self._open = False

    def open(self) -> ThinkingStartEvent | None:
        """Mark a new reasoning block as open; return the event to emit on first chunk."""
        if self._open:
            return None
        self._open = True
        self._current = ""
        return ThinkingStartEvent()

    def append(self, text: str) -> None:
        self._current += text

    def close(self) -> ThinkingDoneEvent | None:
        """Close the open block (if any), persist it, and return the done event."""
        if not self._open:
            return None
        self._open = False
        if self._current:
            self.blocks.append(self._current)
            self._current = ""
        return ThinkingDoneEvent()

    @property
    def is_open(self) -> bool:
        return self._open


async def normalize_agent_events(
    graph: CompiledStateGraph,
    runtime_context: TutorRuntimeContext,
) -> AsyncIterator[tuple[ChatStreamEvent | None, dict | None]]:
    """Run the agent and yield typed events.

    Each yield is ``(event, final_state)``:

    - During the run: ``(ChatStreamEvent, None)``.
    - Once: ``(None, final_state_dict)`` as the terminal yield, carrying
      ``full_response``, ``thinking_blocks``, token counts, and tool outputs.

    Owns the thinking-block state machine (previously duplicated 3x).
    Transient-error retries are intentionally out of scope here.
    """
    thinking = ThinkingState()
    seen_tool = False
    full_response = ""
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    images: list[dict] = []

    config = build_runnable_config(runtime_context)

    llm_logger.info(f"graph.stream project_id={runtime_context.project_id} "
                    f"chat_id={runtime_context.chat_id}")

    try:
        async for event in graph.astream_events(
            {"messages": []},
                config=config,
                context=runtime_context,
                version="v2",
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                reasoning = chunk.additional_kwargs.get("reasoning_content")
                if reasoning:
                    if (start := thinking.open()) is not None:
                        yield start, None
                    thinking.append(reasoning)
                    yield ThinkingEvent(content=reasoning), None
                elif chunk.content:
                    if (done := thinking.close()) is not None:
                        yield done, None
                    full_response += chunk.content
                    yield ContentEvent(content=chunk.content), None

            elif kind == "on_tool_start" and not seen_tool:
                seen_tool = True
                if (done := thinking.close()) is not None:
                    yield done, None
                elif full_response:
                    thinking.blocks.append(full_response)
                    yield ThoughtWrapEvent(), None
                status = TOOL_STATUS_MAP.get(event.get("name", ""), "Обработка") + "..."
                yield StatusEvent(status=status), None
                full_response = ""

            elif kind == "on_tool_end" and event.get("name") in _IMAGE_TOOL_NAMES:
                output = event["data"].get("output")
                update = getattr(output, "update", None)
                if isinstance(update, dict):
                    new_images = [
                        img for img in (update.get("images") or [])
                        if isinstance(img, dict) and img.get("url")
                    ]
                    if new_images:
                        images.extend(new_images)
                        yield ImagesEvent(images=new_images), None

            elif kind == "on_chat_model_end":
                output = event["data"].get("output")
                usage = getattr(output, "usage_metadata", None)
                if usage:
                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    reasoning = (usage.get("output_token_details") or {}).get("reasoning", 0)
                    input_tokens += inp
                    output_tokens += out
                    reasoning_tokens += reasoning
                    llm_logger.info(f"graph.llm_call project_id={runtime_context.project_id} "
                                    f"chat_id={runtime_context.chat_id} "
                                    f"input={inp} output={out} reasoning={reasoning}")
                if (done := thinking.close()) is not None:
                    yield done, None

    except Exception as e:
        llm_logger.error(
            f"graph.stream_error project_id={runtime_context.project_id} "
            f"chat_id={runtime_context.chat_id} error={e}",
            exc_info=True,
        )
        raise

    final_state = {
        "full_response": full_response,
        "thinking_blocks": thinking.blocks,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "images": images,
    }
    llm_logger.info(f"graph.stream_complete project_id={runtime_context.project_id} "
                    f"chat_id={runtime_context.chat_id} had_tools={seen_tool} "
                    f"len={len(full_response)} "
                    f"input={input_tokens} output={output_tokens} reasoning={reasoning_tokens}")
    yield None, final_state


async def stream_chat_response(
    graph: CompiledStateGraph,
    runtime_context: TutorRuntimeContext,
    message_id: int,
    has_large_document: bool,
    token_warning: bool,
) -> AsyncGenerator[str, None]:
    """SSE generator for a single chat turn.

    Yields formatted ``data: …\\n\\n`` frames; persists the assistant message
    and usage log after the agent finishes.
    """
    final_state: dict = {}
    try:
        if has_large_document:
            yield format_sse(
                WarningEvent(warning=("Документ содержит много текста. Обработка может занять больше времени.")))
        if token_warning:
            yield format_sse(WarningEvent(warning="Вы израсходовали более 85% дневного лимита токенов."))

        user_msg = runtime_context.current_user_message
        chat_logger.info(f"stream.start project_id={runtime_context.project_id} "
                         f"chat_id={runtime_context.chat_id} "
                         f"has_images={isinstance(getattr(user_msg, 'content', None), list)}")

        async for event, fs in normalize_agent_events(graph, runtime_context):
            if event is not None:
                yield format_sse(event)
            if fs is not None:
                final_state = fs

        chat_logger.info(f"stream.complete project_id={runtime_context.project_id} "
                         f"chat_id={runtime_context.chat_id} "
                         f"len={len(final_state.get('full_response', ''))}")

        yield format_sse(StatusEvent(status="Сохраняю..."))
        await save_assistant_message(runtime_context, final_state)

        input_tokens = final_state.get("input_tokens", 0)
        output_tokens = final_state.get("output_tokens", 0)
        reasoning_tokens = final_state.get("reasoning_tokens", 0)
        images = final_state.get("images", [])
        images_generated = sum(1 for img in images if img.get("source") == "generated")

        if input_tokens or output_tokens:
            await storage.usage_log.create({
                "user_id": runtime_context.user_id,
                "project_id": runtime_context.project_id,
                "chat_id": runtime_context.chat_id,
                "message_id": message_id,
                "model_name": settings.LLM_MODEL,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "images_generated": images_generated,
            })

        yield format_sse(DoneEvent())

    except asyncio.CancelledError:
        chat_logger.info(f"stream.cancel project_id={runtime_context.project_id} "
                         f"chat_id={runtime_context.chat_id}")
        if final_state.get("full_response"):
            try:
                await save_assistant_message(runtime_context, final_state)
            except Exception as e:
                chat_logger.error(f"stream.save_failed project_id={runtime_context.project_id} "
                                  f"chat_id={runtime_context.chat_id} error={e}")
        raise

    except Exception as e:
        chat_logger.opt(exception=True).error(f"stream.error project_id={runtime_context.project_id} "
                                              f"chat_id={runtime_context.chat_id} error={e}")
        yield format_sse(ErrorEvent(error=str(e)))
