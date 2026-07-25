"""Graph-level tests for off-topic refusal.

classify_intent-based off-topic short-circuit was removed (classify-removal
task, Этап 4) — refusal is now entirely the agent's own decision, signaled
via the `decline_off_topic` tool call and `_search_tools_node` setting
`is_refusal=True`, which `_finalize` reads to skip its forced-search safety
net. These tests drive the real compiled graph with the model faked out, to
prove the wiring itself works end-to-end without hitting a real LLM/DB.
"""

from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel, FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

import chat.graph as graph_module
from chat.state import TutorRuntimeContext
from schemas import ProjectContext


def _ctx(message: str) -> TutorRuntimeContext:
    return TutorRuntimeContext(
        chat_id="test-chat",
        project_id="test-project",
        user_id=uuid4(),
        current_user_message=HumanMessage(content=message),
        project=ProjectContext(
            student_name="Test Student",
            student_level="B1",
            description="",
            existing_vocabulary=[],
            existing_topics=[],
        ),
    )


async def _run_and_get_final_state(graph, ctx: TutorRuntimeContext) -> dict:
    final_state: dict = {}
    async for event in graph.astream_events({"messages": []}, context=ctx, version="v2"):
        if event["event"] == "on_chain_end" and event.get("name") == "LangGraph":
            final_state = event["data"].get("output") or {}
    return final_state


@pytest.mark.unit
async def test_off_topic_message_declined_via_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent calls decline_off_topic, then writes a refusal — no forced search follows."""

    async def fake_get_by_project(_project_id: str) -> list[dict]:
        return []

    refusal_text = "Извините, этот вопрос не связан с изучением английского языка."
    # FakeMessagesListChatModel cycles through real BaseMessage responses (so
    # tool_calls work, unlike FakeListChatModel which only does plain
    # strings) — first call decides to decline, second (after search_tools
    # executes the tool and loops back to agent) writes the actual refusal.
    fake_model = FakeMessagesListChatModel(responses=[
        AIMessage(content="", tool_calls=[
            {"name": "decline_off_topic", "args": {"reason": "рецепт борща не про английский"}, "id": "call_1"},
        ]),
        AIMessage(content=refusal_text),
    ])

    monkeypatch.setattr(graph_module.storage.topic_mastery, "get_by_project", fake_get_by_project)
    monkeypatch.setattr(graph_module, "_llm_with_tools", fake_model)

    graph = graph_module.build_tutor_graph()
    ctx = _ctx("как приготовить борщ")

    final_state = await _run_and_get_final_state(graph, ctx)

    assert final_state.get("is_refusal") is True
    assert final_state.get("search_calls", 0) == 0
    # Forced-search safety net must NOT have fired: no extra "=== Результат
    # обязательного поиска ===" SystemMessage, no second model roundtrip
    # beyond the two fake_model responses (fake_model.i would have wrapped
    # around and been reused if finalize made a 3rd call to it, but finalize
    # calls `_llm_plain`, a different attribute, not `_llm_with_tools` — the
    # decisive check is that forced_search_done stayed unset).
    assert not final_state.get("forced_search_done", False)
    last_message = final_state["messages"][-1]
    assert last_message.content == refusal_text


@pytest.mark.unit
async def test_on_topic_message_still_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression check: removing classify must not break the normal path."""

    async def fake_get_by_project(_project_id: str) -> list[dict]:
        return []

    async def fake_run_search_all(_user_id: str, _query: str) -> str:
        return "(материалов не найдено)"

    class _FakePlainModel:
        """Stands in for `_llm_plain` — the forced-search safety net's tool-free
        follow-up call, expected to fire here since the fake model below
        answers without searching (search_calls stays 0)."""

        async def ainvoke(self, _messages: list) -> AIMessage:
            return AIMessage(content="Привет! (после дополнительного поиска)")

    fake_model = FakeListChatModel(responses=["Привет! Чем помочь с английским?"])

    monkeypatch.setattr(graph_module.storage.topic_mastery, "get_by_project", fake_get_by_project)
    monkeypatch.setattr(graph_module, "_llm_with_tools", fake_model)
    monkeypatch.setattr(graph_module, "_llm_plain", _FakePlainModel())
    monkeypatch.setattr(graph_module, "run_search_all", fake_run_search_all)

    graph = graph_module.build_tutor_graph()
    ctx = _ctx("как дела")

    seen_kinds: list[str] = []
    content = ""
    async for event in graph.astream_events(
        {"messages": []},
            context=ctx,
            version="v2",
            stream_mode="custom",
    ):
        seen_kinds.append(event["event"])
        if event["event"] == "on_chat_model_stream":
            content += event["data"]["chunk"].content

    assert "on_chat_model_start" in seen_kinds
    assert content == "Привет! Чем помочь с английским?"
