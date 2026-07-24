"""Off-topic refusal check for the chat agent.

Historically also chose which RAG corpus(es) to deterministically pre-fetch
for non-refused turns (an Adaptive Engine pedagogical override plus
confidence-based single/ensemble retriever selection) — that whole mechanism
was removed once the agentic search tools (chat/search_tools.py) replaced the
deterministic classify->route pre-fetch entirely (chat/graph.py's `agent` node
decides for itself when/what to search). Off-topic refusal was always
intent-only and never influenced by the Adaptive Engine's decision, so this
simplification doesn't change refusal behavior.
"""

from chat.intent import Intent

REFUSAL_MESSAGE = ("Я помогаю только с изучением английского языка — грамматикой, лексикой и практикой. "
                   "Задайте, пожалуйста, вопрос по английскому.")


def resolve_route(intent: Intent) -> str | None:
    """Return the canned refusal message if this turn should be refused, else ``None``.

    Parameters
    ----------
    intent : Intent
        Output of `chat.intent.classify_intent()` for the current message.

    Returns
    -------
    str or None
        `REFUSAL_MESSAGE` if `intent.intent == "off_topic"`, else `None`.
    """
    if intent.intent == "off_topic":
        return REFUSAL_MESSAGE
    return None
