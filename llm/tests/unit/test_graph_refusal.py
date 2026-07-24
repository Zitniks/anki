"""Graph-level test for the off_topic short-circuit (Epic 1, Task 1.2).

Runs the real compiled graph with `classify_intent` / mastery lookup / the
model mocked out, to prove the wiring itself works end-to-end: an off_topic
message reaches END via the `refuse` node without ever touching `_llm_with_tools`
or a RAG retriever, and the canned message is observable as a custom stream
event (the same "on_chain_stream" / name="LangGraph" shape
`chat.streaming.normalize_agent_events` listens for).
"""

from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

import chat.graph as graph_module
from chat.intent import Intent
from chat.rag_router import REFUSAL_MESSAGE
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


@pytest.mark.unit
async def test_off_topic_message_short_circuits_to_refuse(monkeypatch: pytest.MonkeyPatch) -> None:

    async def fake_classify_intent(_message: str) -> Intent:
        return Intent(intent="off_topic", confidence=0.99)

    async def fake_get_by_project(_project_id: str) -> list[dict]:
        return []

    class _ExplodingModel:

        async def ainvoke(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("the LLM must not be invoked for an off_topic message")

    monkeypatch.setattr(graph_module, "classify_intent", fake_classify_intent)
    monkeypatch.setattr(graph_module.storage.topic_mastery, "get_by_project", fake_get_by_project)
    monkeypatch.setattr(graph_module, "_llm_with_tools", _ExplodingModel())

    graph = graph_module.build_tutor_graph()
    ctx = _ctx("как жарить курицу")

    seen_kinds: list[str] = []
    refusal_chunks: list[dict] = []
    async for event in graph.astream_events(
        {"messages": []},
            context=ctx,
            version="v2",
            stream_mode="custom",
    ):
        seen_kinds.append(event["event"])
        if event["event"] == "on_chain_stream" and event.get("name") == "LangGraph":
            chunk = event["data"].get("chunk")
            if isinstance(chunk, dict) and chunk.get("type") == "refusal":
                refusal_chunks.append(chunk)

    assert "on_chat_model_start" not in seen_kinds
    assert "on_chat_model_stream" not in seen_kinds
    assert len(refusal_chunks) == 1
    assert refusal_chunks[0]["content"] == REFUSAL_MESSAGE


@pytest.mark.unit
async def test_on_topic_message_still_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression check: the new classify->refuse branch must not break the normal path."""

    async def fake_classify_intent(_message: str) -> Intent:
        return Intent(intent="chat", confidence=0.9)

    async def fake_get_by_project(_project_id: str) -> list[dict]:
        return []

    fake_model = FakeListChatModel(responses=["Привет! Чем помочь с английским?"])

    monkeypatch.setattr(graph_module, "classify_intent", fake_classify_intent)
    monkeypatch.setattr(graph_module.storage.topic_mastery, "get_by_project", fake_get_by_project)
    monkeypatch.setattr(graph_module, "_llm_with_tools", fake_model)

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
