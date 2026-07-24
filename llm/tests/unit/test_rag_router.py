"""Unit tests for chat.rag_router.resolve_route — pure logic, no DB/LLM."""

import pytest

from adaptive.engine import AdaptiveDecision
from chat.intent import Intent
from chat.rag_router import REFUSAL_MESSAGE, resolve_route


def _decision(action: str = "continue", topic: str = "Present Simple") -> AdaptiveDecision:
    return AdaptiveDecision(
        action=action,
        topic=topic,
        difficulty="easy",
        reason="test",
        mastery_score=0.5,
        als_score=0.5,
    )


def _intent(intent: str, confidence: float = 0.9, topic: str | None = None) -> Intent:
    return Intent(intent=intent, confidence=confidence, topic=topic)


@pytest.mark.unit
def test_off_topic_refuses_before_engine_override():
    """off_topic must win even when the Adaptive Engine would otherwise force a RAG lookup."""
    route = resolve_route(_decision(action="prerequisite"), _intent("off_topic", confidence=0.99))
    assert route.mode == "refuse"
    assert route.retrievers == []
    assert route.message == REFUSAL_MESSAGE


@pytest.mark.unit
def test_off_topic_refuses_even_at_low_confidence():
    route = resolve_route(_decision(), _intent("off_topic", confidence=0.1))
    assert route.mode == "refuse"
    assert route.message == REFUSAL_MESSAGE


@pytest.mark.unit
@pytest.mark.parametrize(
    ("action", "expected_retriever"),
    [("prerequisite", "explanation"), ("more_examples", "example")],
)
def test_engine_forced_override_still_works_for_on_topic_intent(action: str, expected_retriever: str) -> None:
    route = resolve_route(_decision(action=action), _intent("chat", confidence=0.9))
    assert route.mode == "single"
    assert route.retrievers == [expected_retriever]


@pytest.mark.unit
def test_chat_intent_skips_rag():
    route = resolve_route(_decision(), _intent("chat", confidence=0.9))
    assert route.mode == "none"


@pytest.mark.unit
def test_confident_intent_picks_single_retriever():
    route = resolve_route(_decision(), _intent("explanation", confidence=0.8))
    assert route.mode == "single"
    assert route.retrievers == ["explanation"]


@pytest.mark.unit
def test_low_confidence_falls_back_to_ensemble():
    route = resolve_route(_decision(), _intent("exercise", confidence=0.2))
    assert route.mode == "ensemble"
    assert set(route.retrievers) == {"exercise", "explanation", "example"}
