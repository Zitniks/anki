"""Learning event ingestion for gRPC (Anki `PublishEvent`).

Two writes: a raw `LearningEvent` audit row, then the BKT+ALS upsert via
`TopicMasteryRepository.update_from_event`. Anki has no notion of grammar
topics, so per the MVP decision each word is its own topic
(`"word:{word}"`) — free-text, no catalog registration needed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from grpc_svc.session import ResolvedSession
from repositories import storage


async def publish_event(
    session: ResolvedSession,
    word: str,
    correct: bool,
    response_time_ms: int,
    attempts: int,
    difficulty: str,
) -> dict:
    """Record one Anki review answer as a repetitor learning event.

    Parameters
    ----------
    session : ResolvedSession
        Resolved caller session (scopes the event/mastery to a project).
    word : str
        The reviewed word; becomes the mastery topic as `"word:{word}"`.
    correct : bool
        Whether the student answered correctly.
    response_time_ms : int
        Time taken to answer, in milliseconds.
    attempts : int
        Number of attempts for this round (Anki doesn't track retries per
        round today, so the Go client always sends 1).
    difficulty : str
        Optional free-text difficulty label; may be empty.

    Returns
    -------
    dict
        `{"accepted": True}` once both writes succeed.
    """
    topic = f"word:{word}"
    time_seconds = max(0, response_time_ms // 1000)
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    await storage.learning_events.create({
        "project_id": session.project_id,
        "topic": topic,
        "correct": correct,
        "time_seconds": time_seconds,
        "attempts": attempts or 1,
        "hint_used": False,
        "confidence": None,
        "mistakes": None,
        "difficulty": difficulty or None,
        "exercise_id": None,
        "created_at": now,
    })
    await storage.topic_mastery.update_from_event(
        project_id=session.project_id,
        topic=topic,
        correct=correct,
        time_seconds=time_seconds,
        attempts=attempts or 1,
        hint_used=False,
        confidence=None,
        event_at=now,
    )
    return {"accepted": True}
