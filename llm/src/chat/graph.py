"""LangGraph ``StateGraph`` definition for the tutor agent.

Streaming and event normalization live in :mod:`chat.streaming`; this module
only owns graph construction.
"""

import asyncio
from dataclasses import asdict
from typing import Literal

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from adaptive.engine import decide as adaptive_decide
from analytics.retrievers import (
    ExampleRetriever,
    ExerciseRetriever,
    ExplanationRetriever,
    TutorRetriever,
    reciprocal_rank_fusion,
)
from chat.intent import classify_intent
from chat.persistence import convert_to_langchain_messages
from chat.prompts import SYSTEM_PROMPTS
from chat.rag_router import REFUSAL_MESSAGE, resolve_route
from chat.search_tools import SEARCH_TOOLS
from chat.state import TutorRuntimeContext, TutorState
from chat.tools import TOOLS
from database import async_session_factory
from logger import llm_logger
from repositories import storage
from settings import settings

_TOOL_ERROR_MESSAGE = ("Инструмент завершился ошибкой. Сообщи об этом репетитору одним предложением, "
                       "не пытайся повторно вызывать тот же инструмент с теми же аргументами.")

_llm_with_tools = settings.llm.bind_tools(TOOLS)
_tool_node = ToolNode(TOOLS, handle_tool_errors=_TOOL_ERROR_MESSAGE)

# Agentic RAG branch (settings.AGENTIC_RAG_ENABLED) — the model gets the four
# search tools *in addition to* the existing TOOLS (deck/progress/content
# tools), not instead of them. Those existing tools are untouched and must
# keep working exactly as before inside this branch too (a chat with agentic
# RAG enabled should still be able to add words to the deck, etc.) — this is
# one combined ToolNode rather than two, so a single model turn can freely
# mix a search-tool call with a regular-tool call without either node
# silently failing to find the other's tool.
_llm_with_agentic_tools = settings.llm.bind_tools(TOOLS + SEARCH_TOOLS)
_agentic_tool_node = ToolNode(TOOLS + SEARCH_TOOLS, handle_tool_errors=_TOOL_ERROR_MESSAGE)

_RETRIEVER_CLASSES: dict[str, type[TutorRetriever]] = {
    "exercise": ExerciseRetriever,
    "explanation": ExplanationRetriever,
    "example": ExampleRetriever,
}


def _prepare_messages(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Build the full message list for this turn: system prompt + history + current user message."""
    ctx = runtime.context
    cfg = SYSTEM_PROMPTS.get(ctx.system_prompt_key, SYSTEM_PROMPTS["default"])
    system_text = cfg.build(ctx)

    history_msgs = convert_to_langchain_messages(ctx.history)
    user_msg = [ctx.current_user_message] if ctx.current_user_message is not None else []

    return {
        "messages": [SystemMessage(content=system_text), *history_msgs, *user_msg],
        "images": [],
    }


async def _call_model(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    response = await _llm_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}


def _should_continue(state: TutorState) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def _extract_text(message: HumanMessage) -> str:
    """Pull the plain-text part out of a ``HumanMessage`` (content may be a string or content blocks)."""
    if isinstance(message.content, str):
        return message.content
    for block in message.content:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")
    return ""


async def _classify(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Determine which RAG (if any) this turn needs.

    Combines the Adaptive Engine's pedagogical decision (hard priority) with
    an LLM intent classification of the student's message. See
    :func:`chat.rag_router.resolve_route` for the priority rules.
    """
    ctx = runtime.context
    if ctx.current_user_message is None:
        return {"route_decision": None}

    query = _extract_text(ctx.current_user_message)
    if not query:
        return {"route_decision": None}

    intent = await classify_intent(query)
    mastery_records = await storage.topic_mastery.get_by_project(ctx.project_id)
    engine_decision = adaptive_decide(mastery_records)

    route = resolve_route(engine_decision, intent)
    llm_logger.info(
        f"chat.rag_classify project_id={ctx.project_id} intent={intent.intent} "
        f"confidence={intent.confidence:.2f} engine_action={engine_decision.action} "
        f"route_mode={route.mode} retrievers={route.retrievers} reason={route.reason!r}")
    # `intent`/`confidence` are extra keys on top of RouteDecision's own fields
    # (mode/retrievers/topic/reason/message) — additive, so the router branch
    # (which only ever reads mode/retrievers/topic) is unaffected. The agentic
    # branch's prompt hint (Этап 3, AGENTIC_SEARCH_POLICY) needs these to tell
    # the model "Вероятное намерение: X, уверенность Y" without re-running the
    # classifier a second time.
    return {"route_decision": {**asdict(route), "intent": intent.intent, "confidence": intent.confidence}}


async def _refuse(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Return the canned off-topic refusal without invoking the LLM or any RAG retriever.

    Emits the text via a custom stream event (picked up by
    ``chat.streaming.normalize_agent_events``) instead of an LLM call, since no
    ``on_chat_model_stream``/``on_chat_model_end`` event would otherwise fire
    for this turn.
    """
    route_data = state.get("route_decision") or {}
    message = route_data.get("message") or REFUSAL_MESSAGE
    get_stream_writer()({"type": "refusal", "content": message})
    return {"messages": [AIMessage(content=message)]}


def _route_or_refuse(state: TutorState) -> Literal["route", "refuse"]:
    route_data = state.get("route_decision")
    if route_data and route_data.get("mode") == "refuse":
        return "refuse"
    return "route"


def _format_documents(docs: list[Document], max_chars: int = 3000) -> str:
    """Assemble retrieved documents into a context block for LLM injection."""
    if not docs:
        return ""

    lines = ["=== Retrieved Context ==="]
    total = 0
    for i, doc in enumerate(docs, 1):
        label = doc.metadata.get("source", "unknown")
        block = f"\n[{i}] ({label})\n{doc.page_content[:800]}\n---"
        if total + len(block) > max_chars:
            break
        lines.append(block)
        total += len(block)
    return "\n".join(lines)


async def _route(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Query the retriever(s) chosen by ``_classify`` and inject their context."""
    route_data = state.get("route_decision")
    if not route_data or route_data["mode"] == "none":
        return {}

    ctx = runtime.context
    query = _extract_text(ctx.current_user_message) if ctx.current_user_message else ""
    if not query:
        return {}

    user_id = str(ctx.user_id)
    topic = route_data.get("topic")
    retrievers = [
        _RETRIEVER_CLASSES[name](session_factory=async_session_factory, user_id=user_id, topic=topic, limit=5)
        for name in route_data["retrievers"]
    ]

    if route_data["mode"] == "ensemble":
        result_sets = await asyncio.gather(*(r.ainvoke(query) for r in retrievers))
        docs = reciprocal_rank_fusion(list(result_sets))
    else:
        docs = await retrievers[0].ainvoke(query)

    llm_logger.info(
        f"chat.rag_route project_id={ctx.project_id} mode={route_data['mode']} "
        f"retrievers={route_data['retrievers']} found={len(docs)}")

    context = _format_documents(docs)
    return {"messages": [SystemMessage(content=context)]} if context else {}


# ===========================================================================
# Agentic RAG branch (settings.AGENTIC_RAG_ENABLED) — hybrid schema:
#   prepare -> classify -> agent <-> search_tools -> finalize -> end
# `classify` is shared with the router branch (still resolves off-topic
# refusal), but its RouteDecision no longer drives a deterministic RAG
# pre-fetch here — it's injected into the prompt as a hint only (Этап 3).
# ===========================================================================


async def _call_agentic_model(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    response = await _llm_with_agentic_tools.ainvoke(state["messages"])
    return {"messages": [response]}


def _agentic_should_continue(state: TutorState) -> Literal["search_tools", "finalize"]:
    last = state["messages"][-1]
    return "search_tools" if getattr(last, "tool_calls", None) else "finalize"


def _classify_or_refuse_agentic(state: TutorState) -> Literal["agent", "refuse"]:
    route_data = state.get("route_decision")
    if route_data and route_data.get("mode") == "refuse":
        return "refuse"
    return "agent"


async def _finalize(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Terminal node of the agentic branch. Passthrough for now — the
    skip-search / forced-retry safety net is added in Этап 4."""
    return {}


def build_tutor_graph() -> CompiledStateGraph:
    """Build and compile the tutor LangGraph.

    Branch choice (router vs. agentic RAG) is made here, once, at build time
    — not inside a conditional-edge function re-checked per turn — so the
    router branch's graph structure is exactly what it was before
    AGENTIC_RAG_ENABLED existed when the flag is off.
    """
    builder = StateGraph(TutorState, context_schema=TutorRuntimeContext)
    builder.add_node("prepare", _prepare_messages)
    builder.add_node("classify", _classify)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "classify")

    if settings.AGENTIC_RAG_ENABLED:
        builder.add_node("agent", _call_agentic_model)
        builder.add_node("search_tools", _agentic_tool_node)
        builder.add_node("refuse", _refuse)
        builder.add_node("finalize", _finalize)
        builder.add_conditional_edges("classify", _classify_or_refuse_agentic)
        builder.add_conditional_edges("agent", _agentic_should_continue)
        builder.add_edge("search_tools", "agent")
        builder.add_edge("refuse", END)
        builder.add_edge("finalize", END)
    else:
        builder.add_node("route", _route)
        builder.add_node("refuse", _refuse)
        builder.add_node("model", _call_model)
        builder.add_node("tools", _tool_node)
        builder.add_conditional_edges("classify", _route_or_refuse)
        builder.add_edge("route", "model")
        builder.add_edge("refuse", END)
        builder.add_conditional_edges("model", _should_continue)
        builder.add_edge("tools", "model")

    return builder.compile()
