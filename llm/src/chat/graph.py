"""LangGraph ``StateGraph`` definition for the tutor agent.

Streaming and event normalization live in :mod:`chat.streaming`; this module
only owns graph construction.

Agentic RAG only — the model decides when/what to search via the tools in
``chat/search_tools.py`` instead of a deterministic classify->route pre-fetch.
The router-based predecessor (a fixed classify->route->model loop with
``chat/rag_router.py::resolve_route`` choosing which corpus to pre-fetch)
was removed once this branch was proven out (see git history and
scripts/eval_agentic_rag.py for the router-vs-agentic comparison it replaced).
"""

import time
from dataclasses import asdict
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from adaptive.engine import decide as adaptive_decide
from chat.intent import classify_intent
from chat.persistence import convert_to_langchain_messages
from chat.prompts import AGENTIC_INTENT_HINT_TEMPLATE, SYSTEM_PROMPTS
from chat.rag_router import REFUSAL_MESSAGE, resolve_route
from chat.search_tools import SEARCH_TOOLS, _SEARCH_TOOL_CORPUS, _SEARCH_TOOL_NAMES, run_search_all
from chat.state import TutorRuntimeContext, TutorState
from chat.tools import TOOLS
from logger import llm_logger
from repositories import storage
from settings import settings

_TOOL_ERROR_MESSAGE = ("Инструмент завершился ошибкой. Сообщи об этом репетитору одним предложением, "
                       "не пытайся повторно вызывать тот же инструмент с теми же аргументами.")

# The model gets the four search tools *in addition to* the existing TOOLS
# (deck/progress/content tools), not instead of them — one combined
# bind_tools/ToolNode rather than two, so a single model turn can freely mix
# a search-tool call with a regular-tool call without either node silently
# failing to find the other's tool.
_llm_with_tools = settings.llm.bind_tools(TOOLS + SEARCH_TOOLS)
_tool_node = ToolNode(TOOLS + SEARCH_TOOLS, handle_tool_errors=_TOOL_ERROR_MESSAGE)
# Tool-free — used only by `_finalize`'s forced-retry model call, which must
# not be able to request another tool (that branch is a dead end: finalize
# only has an edge to END, no way back into agent/search_tools).
_llm_plain = settings.llm


async def _prepare_messages(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Build the full message list for this turn: system prompt + history + current user message.

    Also fires the Adaptive Engine's pedagogical decision purely for
    observability/logging (`engine_action`) — moved here from `_classify`
    (Этап 2 of the classify-removal task) since it's a pure function plus one
    DB read, no LLM call, and no bearing on this turn's routing (that
    mechanism was already removed earlier — see chat/rag_router.py). Keeping
    the log line here decouples it from `classify`, which Этап 4 removes.
    """
    ctx = runtime.context
    cfg = SYSTEM_PROMPTS.get(ctx.system_prompt_key, SYSTEM_PROMPTS["default"])
    system_text = cfg.build(ctx)

    history_msgs = convert_to_langchain_messages(ctx.history)
    user_msg = [ctx.current_user_message] if ctx.current_user_message is not None else []

    mastery_records = await storage.topic_mastery.get_by_project(ctx.project_id)
    engine_decision = adaptive_decide(mastery_records)
    llm_logger.info(f"chat.adaptive_engine project_id={ctx.project_id} engine_action={engine_decision.action}")

    return {
        "messages": [SystemMessage(content=system_text), *history_msgs, *user_msg],
        "images": [],
    }


def _extract_text(message: HumanMessage) -> str:
    """Pull the plain-text part out of a ``HumanMessage`` (content may be a string or content blocks)."""
    if isinstance(message.content, str):
        return message.content
    for block in message.content:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")
    return ""


async def _classify(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Off-topic gate + intent hint for the agent.

    `adaptive_decide`/`engine_action` logging used to live here too — moved
    to `_prepare_messages` (Этап 2) since it has nothing to do with intent
    classification or the LLM call this node makes.
    """
    ctx = runtime.context
    if ctx.current_user_message is None:
        return {"route_decision": None}

    query = _extract_text(ctx.current_user_message)
    if not query:
        return {"route_decision": None}

    intent = await classify_intent(query)
    refusal = resolve_route(intent)

    llm_logger.info(
        f"chat.classify project_id={ctx.project_id} intent={intent.intent} "
        f"confidence={intent.confidence:.2f} refuse={refusal is not None}")

    hint = AGENTIC_INTENT_HINT_TEMPLATE.format(intent=intent.intent, confidence=intent.confidence)
    return {
        "route_decision": {"refuse": refusal is not None, "message": refusal,
                            "intent": intent.intent, "confidence": intent.confidence},
        "messages": [SystemMessage(content=hint)],
        # Этап 4 timeout budget: stamped once here (classify runs exactly once
        # per turn, before the agent<->search_tools loop), checked by
        # `_agentic_should_continue` on every iteration of that loop.
        "agentic_deadline": time.monotonic() + settings.AGENTIC_RAG_TIMEOUT_SECONDS,
    }


async def _refuse(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Return the canned off-topic refusal without invoking the LLM or any search tool.

    Emits the text via a custom stream event (picked up by
    ``chat.streaming.normalize_agent_events``) instead of an LLM call, since no
    ``on_chat_model_stream``/``on_chat_model_end`` event would otherwise fire
    for this turn.
    """
    route_data = state.get("route_decision") or {}
    message = route_data.get("message") or REFUSAL_MESSAGE
    get_stream_writer()({"type": "refusal", "content": message})
    return {"messages": [AIMessage(content=message)]}


def _classify_or_refuse(state: TutorState) -> Literal["agent", "refuse"]:
    route_data = state.get("route_decision")
    if route_data and route_data.get("refuse"):
        return "refuse"
    return "agent"


async def _call_model(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    response = await _llm_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}


def _should_continue(state: TutorState) -> Literal["search_tools", "finalize"]:
    last = state["messages"][-1]
    if not getattr(last, "tool_calls", None):
        return "finalize"
    deadline = state.get("agentic_deadline")
    if deadline is not None and time.monotonic() >= deadline:
        # Budget's up — `finalize` still owes a ToolMessage for every pending
        # tool_call on `last` (LangChain requires one per call_id), so it
        # can't just be dropped here; `_finalize` stubs them out.
        return "finalize"
    return "search_tools"


def _tool_call_key(name: str, args: dict) -> tuple:
    return (name, tuple(sorted(args.items())))


async def _search_tools_node(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Executes pending tool calls for the ``agent`` node.

    Wraps the plain ``ToolNode(TOOLS + SEARCH_TOOLS)`` (still used for actual
    execution, so ``ToolRuntime`` injection stays correct) with three things
    a stock ``ToolNode`` can't do on its own: per-turn search-call
    counting/limiting, anti-loop deduplication, and
    ``corpora_used``/``retrieved_docs`` tracking (used by
    scripts/eval_agentic_rag.py). Every tool_call still gets exactly one
    ToolMessage (some real, some synthetic stubs for skipped/duplicate calls)
    — never left dangling.
    """
    last = state["messages"][-1]
    calls = getattr(last, "tool_calls", None) or []

    search_calls_so_far = state.get("search_calls", 0)
    retrieved_docs = list(state.get("retrieved_docs", []))
    corpora_used = set(state.get("corpora_used", set()))
    last_search_key = _tool_call_key(retrieved_docs[-1]["name"], retrieved_docs[-1]["args"]) if retrieved_docs else None

    to_execute: list[dict] = []
    stub_messages: list[ToolMessage] = []
    new_search_calls = 0

    for call in calls:
        name = call["name"]
        args = call.get("args", {})
        if name not in _SEARCH_TOOL_NAMES:
            to_execute.append(call)
            continue

        key = _tool_call_key(name, args)
        if key == last_search_key:
            cached = retrieved_docs[-1]["result"]
            llm_logger.info(f"search_tool.dedup name={name} args={args} — identical to previous call, skipped")
            stub_messages.append(ToolMessage(
                content=f"[повторный запрос — использован результат предыдущего вызова]\n{cached}",
                tool_call_id=call["id"], name=name))
            continue

        if search_calls_so_far + new_search_calls >= settings.AGENTIC_RAG_SEARCH_CALL_LIMIT:
            llm_logger.info(f"search_tool.limit_reached name={name} args={args} "
                            f"limit={settings.AGENTIC_RAG_SEARCH_CALL_LIMIT}")
            stub_messages.append(ToolMessage(
                content=f"Лимит поисковых запросов ({settings.AGENTIC_RAG_SEARCH_CALL_LIMIT}) на этот ход исчерпан.",
                tool_call_id=call["id"], name=name))
            continue

        to_execute.append(call)
        new_search_calls += 1
        last_search_key = key  # a 2nd distinct search call in the same batch still dedups against this one

    result_messages: list = list(stub_messages)
    if to_execute:
        stub_ai_message = AIMessage(content="", tool_calls=to_execute)
        tool_result = await _tool_node.ainvoke({"messages": [stub_ai_message]})
        executed_msgs = tool_result["messages"]
        result_messages.extend(executed_msgs)

        by_id = {call["id"]: call for call in to_execute}
        for msg in executed_msgs:
            call = by_id.get(msg.tool_call_id)
            if call is None or call["name"] not in _SEARCH_TOOL_NAMES:
                continue
            retrieved_docs.append({"name": call["name"], "args": call.get("args", {}), "result": msg.content})
            corpora_used.add(_SEARCH_TOOL_CORPUS.get(call["name"], call["name"]))

    return {
        "messages": result_messages,
        "search_calls": search_calls_so_far + new_search_calls,
        "retrieved_docs": retrieved_docs,
        "corpora_used": corpora_used,
    }


_EDUCATIONAL_INTENTS = {"exercise", "explanation", "example"}
_SKIP_SEARCH_CONFIDENCE_THRESHOLD = 0.6


async def _finalize(state: TutorState, runtime: Runtime[TutorRuntimeContext]) -> dict:
    """Terminal node of the graph.

    Two responsibilities:
    1. If reached via the iteration-limit/timeout bypass in
       `_should_continue` (skipping `search_tools` entirely), the last
       AIMessage may still have unresolved tool_calls — stub them so every
       call_id gets exactly one ToolMessage.
    2. Skip-search safety net: an educational-intent turn that made it all
       the way here without ever searching gets exactly one forced
       `search_all` pass + one more (tool-free) model call. Guarded by
       `forced_search_done` so this can only ever fire once per turn.
    """
    messages = state["messages"]
    last = messages[-1] if messages else None
    ctx = runtime.context

    stub_messages: list[ToolMessage] = []
    if last is not None and getattr(last, "tool_calls", None):
        for call in last.tool_calls:
            stub_messages.append(ToolMessage(
                content="Инструмент не был вызван — превышен лимит поисков или таймаут на этот ход.",
                tool_call_id=call["id"], name=call.get("name", "")))

    route_data = state.get("route_decision") or {}
    intent = route_data.get("intent")
    confidence = route_data.get("confidence", 0.0)
    search_calls = state.get("search_calls", 0)

    should_force_search = (
        not stub_messages
        and not state.get("forced_search_done", False)
        and search_calls == 0
        and intent in _EDUCATIONAL_INTENTS
        and confidence > _SKIP_SEARCH_CONFIDENCE_THRESHOLD
    )
    if not should_force_search:
        return {"messages": stub_messages} if stub_messages else {}

    query = _extract_text(ctx.current_user_message) if ctx.current_user_message else ""
    if not query:
        return {"messages": stub_messages} if stub_messages else {}

    llm_logger.info(f"chat.forced_search project_id={ctx.project_id} intent={intent} "
                    f"confidence={confidence:.2f} reason='search_calls=0 on educational intent'")
    forced_result = await run_search_all(str(ctx.user_id), query)
    forced_context = SystemMessage(
        content=f"=== Результат обязательного поиска (студент не получил ответ без него) ===\n{forced_result}")

    # Tool-free model call: guarantees no new tool_calls can appear, so this
    # branch can safely be a dead end (finalize -> END, no way back into
    # agent/search_tools — "второй раз в эту ветку заходить нельзя").
    final_messages = [*messages, forced_context]
    response = await _llm_plain.ainvoke(final_messages)

    return {
        "messages": [forced_context, response],
        "forced_search_done": True,
    }


def build_tutor_graph() -> CompiledStateGraph:
    """Build and compile the tutor LangGraph: prepare -> classify -> agent <-> search_tools -> finalize -> end."""
    builder = StateGraph(TutorState, context_schema=TutorRuntimeContext)
    builder.add_node("prepare", _prepare_messages)
    builder.add_node("classify", _classify)
    builder.add_node("agent", _call_model)
    builder.add_node("search_tools", _search_tools_node)
    builder.add_node("refuse", _refuse)
    builder.add_node("finalize", _finalize)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "classify")
    builder.add_conditional_edges("classify", _classify_or_refuse)
    builder.add_conditional_edges("agent", _should_continue)
    builder.add_edge("search_tools", "agent")
    builder.add_edge("refuse", END)
    builder.add_edge("finalize", END)
    return builder.compile()
