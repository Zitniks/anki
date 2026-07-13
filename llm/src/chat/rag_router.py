"""Priority logic for choosing which RAG corpus (if any) to query this turn.

Pure functions — no I/O — so this is unit-testable without a DB or LLM.
"""

from dataclasses import dataclass, field
from typing import Literal

from adaptive.engine import AdaptiveDecision
from chat.intent import Intent

# Adaptive Engine actions that force a specific RAG regardless of what the
# student's wording suggests. Actions not listed here (repeat,
# increase_difficulty, decrease_difficulty, next_topic) don't override —
# they fall through to the classifier.
_ENGINE_FORCED_INTENT: dict[str, str] = {
    "prerequisite": "explanation",   # student is missing foundational understanding
    "more_examples": "example",      # Engine's own rule already asks for more examples
}

_CONFIDENCE_THRESHOLD = 0.5

RetrieverName = Literal["exercise", "explanation", "example"]


@dataclass
class RouteDecision:
    mode: Literal["single", "ensemble", "none"]
    retrievers: list[RetrieverName] = field(default_factory=list)
    topic: str | None = None
    reason: str = ""


def resolve_route(engine_decision: AdaptiveDecision, intent: Intent) -> RouteDecision:
    """Decide which RAG retriever(s), if any, to query this turn.

    Priority:
    1. Adaptive Engine forced override (`_ENGINE_FORCED_INTENT`) — a
       pedagogical decision wins regardless of message wording.
    2. `chat` intent -> no RAG.
    3. Confident classifier intent -> that one corpus.
    4. Low-confidence, non-chat intent -> ensemble of all three corpora.

    Parameters
    ----------
    engine_decision : AdaptiveDecision
        Output of `adaptive.engine.decide()` for the student's current topic.
    intent : Intent
        Output of `chat.intent.classify_intent()` for the current message.

    Returns
    -------
    RouteDecision
    """
    forced = _ENGINE_FORCED_INTENT.get(engine_decision.action)
    if forced:
        return RouteDecision(
            mode="single",
            retrievers=[forced],  # type: ignore[list-item]
            topic=engine_decision.topic,
            reason=f"adaptive engine action={engine_decision.action!r} forces {forced!r}",
        )

    if intent.intent == "chat":
        return RouteDecision(mode="none", reason="intent=chat")

    if intent.confidence >= _CONFIDENCE_THRESHOLD:
        return RouteDecision(
            mode="single",
            retrievers=[intent.intent],  # type: ignore[list-item]
            topic=intent.topic,
            reason=f"classifier intent={intent.intent!r} confidence={intent.confidence:.2f}",
        )

    return RouteDecision(
        mode="ensemble",
        retrievers=["exercise", "explanation", "example"],
        topic=intent.topic,
        reason=f"low confidence ({intent.confidence:.2f}) — ensemble fallback",
    )
