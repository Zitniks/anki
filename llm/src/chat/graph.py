"""LangGraph ``StateGraph`` definition for the tutor agent.

Streaming and event normalization live in :mod:`chat.streaming`; this module
only owns graph construction.
"""

import asyncio
from dataclasses import asdict
from typing import Literal

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from adaptive.engine import decide as adaptive_decide
from analytics.retrievers import ExampleRetriever, ExerciseRetriever, ExplanationRetriever, TutorRetriever
from chat.intent import classify_intent
from chat.persistence import convert_to_langchain_messages
from chat.prompts import SYSTEM_PROMPTS
from chat.rag_router import resolve_route
from chat.state import TutorRuntimeContext, TutorState
from chat.tools import TOOLS
from database import async_session_factory
from logger import llm_logger
from repositories import storage
from settings import settings

_llm_with_tools = settings.llm.bind_tools(TOOLS)
_tool_node = ToolNode(
    TOOLS,
    handle_tool_errors=(
        "Инструмент завершился ошибкой. Сообщи об этом репетитору одним предложением, "
        "не пытайся повторно вызывать тот же инструмент с теми же аргументами."),
)

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
    return {"route_decision": asdict(route)}


def _reciprocal_rank_fusion(result_sets: list[list[Document]], k: int = 60) -> list[Document]:
    """Merge multiple ranked ``Document`` lists into one, highest combined rank first."""
    scores: dict[str, float] = {}
    docs_by_key: dict[str, Document] = {}
    for docs in result_sets:
        for rank, doc in enumerate(docs):
            key = doc.page_content
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            docs_by_key.setdefault(key, doc)
    ranked_keys = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [docs_by_key[key] for key in ranked_keys]


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
        docs = _reciprocal_rank_fusion(list(result_sets))
    else:
        docs = await retrievers[0].ainvoke(query)

    llm_logger.info(
        f"chat.rag_route project_id={ctx.project_id} mode={route_data['mode']} "
        f"retrievers={route_data['retrievers']} found={len(docs)}")

    context = _format_documents(docs)
    return {"messages": [SystemMessage(content=context)]} if context else {}


def build_tutor_graph() -> CompiledStateGraph:
    """Build and compile the tutor LangGraph."""
    builder = StateGraph(TutorState, context_schema=TutorRuntimeContext)
    builder.add_node("prepare", _prepare_messages)
    builder.add_node("classify", _classify)
    builder.add_node("route", _route)
    builder.add_node("model", _call_model)
    builder.add_node("tools", _tool_node)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "classify")
    builder.add_edge("classify", "route")
    builder.add_edge("route", "model")
    builder.add_conditional_edges("model", _should_continue)
    builder.add_edge("tools", "model")
    return builder.compile()
