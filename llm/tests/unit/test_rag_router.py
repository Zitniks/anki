"""Unit tests for chat.rag_router.resolve_route — pure logic, no DB/LLM.

Only off-topic refusal remains here — the engine-forced-override/retriever-
selection logic this used to also cover was removed along with the
deterministic router branch it powered (chat/graph.py's `agent` node decides
for itself when/what to search via chat/search_tools.py now).
"""

import pytest

from chat.intent import Intent
from chat.rag_router import REFUSAL_MESSAGE, resolve_route


def _intent(intent: str, confidence: float = 0.9, topic: str | None = None) -> Intent:
    return Intent(intent=intent, confidence=confidence, topic=topic)


@pytest.mark.unit
def test_off_topic_refuses():
    assert resolve_route(_intent("off_topic", confidence=0.99)) == REFUSAL_MESSAGE


@pytest.mark.unit
def test_off_topic_refuses_even_at_low_confidence():
    assert resolve_route(_intent("off_topic", confidence=0.1)) == REFUSAL_MESSAGE


@pytest.mark.unit
@pytest.mark.parametrize("intent", ["chat", "explanation", "exercise", "example"])
def test_on_topic_intents_are_not_refused(intent: str) -> None:
    assert resolve_route(_intent(intent, confidence=0.9)) is None
