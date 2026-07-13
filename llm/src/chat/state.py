"""Graph state and runtime context types for the tutor agent."""

import operator
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from schemas import ProjectContext
from settings import settings


class TutorRuntimeContext(BaseModel):
    """Immutable per-turn inputs passed to the graph via ``context=``."""

    model_config = {"arbitrary_types_allowed": True, "frozen": True}

    chat_id: str
    project_id: str
    user_id: UUID
    history: list[dict] = Field(default_factory=list)
    documents_context: str = "Документы не загружены."
    system_prompt_key: str = "default"
    include_student_description: bool = True
    project: ProjectContext | None = None
    current_user_message: HumanMessage | None = None


def build_runnable_config(
    ctx: TutorRuntimeContext,
    attempt: int = 0,
    *,
    extra_metadata: dict[str, Any] | None = None,
    extra_callbacks: list | None = None,
) -> RunnableConfig:
    """Build the LangGraph ``RunnableConfig`` for a single agent invocation.

    Single source of truth for the per-turn config. Populates ``thread_id``,
    ``run_id``, identity, metadata, tags, callbacks and ``recursion_limit``
    so tracing / future feedback hooks have everything they need.

    Parameters
    ----------
    ctx : TutorRuntimeContext
        Per-turn immutable inputs.
    attempt : int
        Retry attempt (0 = first). Recorded in metadata for tracing.
    extra_metadata : dict, optional
        Additional metadata merged into the config (e.g. prompt key).
    extra_callbacks : list, optional
        Additional LangChain callbacks appended after the Langfuse handler.

    Returns
    -------
    RunnableConfig
        Config dict suitable for ``astream_events``.
    """
    metadata: dict[str, Any] = {
        "chat_id": ctx.chat_id,
        "project_id": ctx.project_id,
        "user_id": str(ctx.user_id),
        "attempt": attempt,
        "prompt_key": ctx.system_prompt_key,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    # Langfuse callbacks are already bound to settings.llm at construction time,
    # so we don't re-attach them here (would double-trace).
    callbacks: list = list(extra_callbacks) if extra_callbacks else []

    cfg: RunnableConfig = {
        "configurable": {
            "thread_id": ctx.chat_id,
            "user_id": str(ctx.user_id),
            "project_id": ctx.project_id,
        },
        "run_id": uuid4(),
        "metadata": metadata,
        "tags": [f"chat:{ctx.chat_id}", f"prompt:{ctx.system_prompt_key}"],
        "recursion_limit": settings.GRAPH_RECURSION_LIMIT,
    }
    if callbacks:
        cfg["callbacks"] = callbacks
    return cfg


class TutorState(MessagesState):
    """Graph state — outputs the agent reads, writes, and checkpoints.

    Inherits ``messages`` (with the ``add_messages`` reducer) from
    ``MessagesState``. Only tool-produced and graph-node side outputs live
    here; values derivable from ``messages`` (token counts, full text
    response) or only available during streaming (reasoning chunks) stay as
    streaming locals in :func:`chat.streaming.normalize_agent_events`.
    """

    images: Annotated[list[dict], operator.add]
    route_decision: dict | None
