"""LLM-based intent classification for RAG routing.

First use of LangChain structured output in this codebase — bound once at
import time, same pattern as `_llm_with_tools` in `chat/graph.py`. Uses
`settings.llm_cheap` (the same fast/cheap tier already used for vocabulary
extraction and chat-name generation). `method="function_calling"` is used
instead of the newer `json_schema` default because this deployment's
OpenAI-compatible backend is only proven to support tool calling
(`settings.llm.bind_tools` is already relied on elsewhere).
"""

from typing import Literal

from pydantic import BaseModel, Field

from settings import settings


class Intent(BaseModel):
    """Structured output of the intent classifier."""

    intent: Literal["exercise", "explanation", "example", "chat"] = Field(
        description="What kind of RAG corpus (if any) this message needs.")
    topic: str | None = Field(default=None, description="Grammar topic mentioned or implied, if any.")
    confidence: float = Field(ge=0.0, le=1.0, description="Classifier's confidence in `intent`.")


_CLASSIFIER_PROMPT = """Classify what the student is asking for in their message.

- "exercise": they want a practice exercise/task to do.
- "explanation": they want a grammar rule or concept explained.
- "example": they want example sentences showing usage.
- "chat": none of the above (greeting, feedback, unrelated question).

Extract the grammar topic if one is mentioned or clearly implied (e.g. "Present Perfect").
If no topic is mentioned, leave it null.

Student message: {message}"""

_classifier = settings.llm_cheap.with_structured_output(Intent, method="function_calling")


async def classify_intent(message: str) -> Intent:
    """Classify a student's chat message into a RAG intent.

    Parameters
    ----------
    message : str
        The student's current chat message.

    Returns
    -------
    Intent
    """
    return await _classifier.ainvoke(_CLASSIFIER_PROMPT.format(message=message))
