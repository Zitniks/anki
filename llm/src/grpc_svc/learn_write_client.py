"""Reverse channel (Epic 2): client for ankis' LearnWriteService.

The opposite direction from this process' own TutorService server (see
grpc_svc/servicer.py) — here llm-service is the gRPC CLIENT, calling back
into a specific Anki Lite user's own vocabulary deck (back/'s ankis-db) on
behalf of the chat agent, mid-conversation. Plain unary RPCs (topology "A"
from IMPROVEMENTS_SPEC.md Epic 2) — no correlation/stream-callback machinery.

If ankis is unreachable, calls raise ``grpc.aio.AioRpcError`` like any other
gRPC call — callers (chat tools) are expected to catch it and degrade to a
friendly message rather than let it bubble into the agent's response.
"""

from __future__ import annotations

import grpc

from grpc_svc.pb.tutor.v1 import tutor_pb2, tutor_pb2_grpc
from settings import settings

_channel: grpc.aio.Channel | None = None


def _stub() -> tutor_pb2_grpc.LearnWriteServiceStub:
    global _channel
    if _channel is None:
        _channel = grpc.aio.insecure_channel(settings.LEARN_WRITE_GRPC_ADDR)
    return tutor_pb2_grpc.LearnWriteServiceStub(_channel)


async def add_words(anki_user_id: int, words: list[dict]) -> list[dict]:
    """Add drafted words to the Anki user's own vocabulary deck.

    Parameters
    ----------
    anki_user_id : int
        The Anki Lite (Go/ankis-db) user id — TutorRuntimeContext.anki_user_id.
    words : list of dict
        Each with keys ``word``, ``translation``, and optionally ``example``/
        ``transcription``.

    Returns
    -------
    list of dict
        One per input word: ``{"word", "added", "reason"}`` — ``reason`` is
        only set when ``added`` is False (e.g. "already exists").
    """
    request = tutor_pb2.AddWordsRequest(
        user_id=anki_user_id,
        words=[
            tutor_pb2.WordDraft(
                word=w["word"],
                translation=w.get("translation", ""),
                example=w.get("example", ""),
                transcription=w.get("transcription", ""),
            )
            for w in words
        ],
    )
    response = await _stub().AddWords(request)
    return [{"word": r.word, "added": r.added, "reason": r.reason} for r in response.results]


async def delete_word(anki_user_id: int, word: str) -> bool:
    """Delete one word (by exact text, case-insensitive) from the user's deck.

    Returns
    -------
    bool
        True if a word was actually deleted; False if no such word existed.
    """
    response = await _stub().DeleteWord(tutor_pb2.DeleteWordRequest(user_id=anki_user_id, word=word))
    return response.deleted


async def check_words_exist(anki_user_id: int, words: list[str]) -> list[dict]:
    """Check which of the given words are already in the user's deck.

    Returns
    -------
    list of dict
        One per input word: ``{"word", "exists", "translation"}`` —
        ``translation`` is only populated when ``exists`` is True.
    """
    response = await _stub().CheckWordsExist(
        tutor_pb2.CheckWordsExistRequest(user_id=anki_user_id, words=words)
    )
    return [{"word": r.word, "exists": r.exists, "translation": r.translation} for r in response.results]
