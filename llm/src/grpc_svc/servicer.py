"""gRPC servicer implementing tutor.v1.TutorService."""

from __future__ import annotations

import grpc
from google.protobuf import empty_pb2
from langgraph.graph.state import CompiledStateGraph
from typing import AsyncIterator
from uuid import UUID

from chat.lifecycle import _build_user_message
from chat.persistence import load_context, save_user_message
from chat.state import TutorRuntimeContext
from chat.streaming import normalize_agent_events
from database import async_session_factory
from grpc_svc.enrich import enrich_word
from grpc_svc.events import publish_event
from grpc_svc.explain import explain_error
from grpc_svc.pb.tutor.v1 import tutor_pb2, tutor_pb2_grpc
from grpc_svc.practice import generate_practice
from grpc_svc.session import ResolvedSession, resolve_session
from analytics.example_bank import search_examples
from analytics.knowledge_docs import search_explanations
from analytics.rag import build_context, search
from logger import chat_logger
from repositories import storage


def _status_response(session: ResolvedSession | None, *, ready: bool, address: str, error: str = "") -> tutor_pb2.StatusResponse:
    resp = tutor_pb2.StatusResponse(ready=ready, address=address, error=error)
    if session is not None:
        resp.project_id = session.project_id
        resp.chat_id = session.chat_id
        resp.practice_chat_id = session.practice_chat_id
    return resp


def _chat_event(event_type: str, **kwargs) -> tutor_pb2.ChatEvent:
    return tutor_pb2.ChatEvent(type=event_type, **kwargs)


class TutorGrpcServicer(tutor_pb2_grpc.TutorServiceServicer):
    def __init__(self, graph: CompiledStateGraph, address: str) -> None:
        self._graph = graph
        self._address = address

    async def Health(self, request: empty_pb2.Empty, context: grpc.aio.ServicerContext) -> tutor_pb2.StatusResponse:
        return tutor_pb2.StatusResponse(ready=True, address=self._address)

    async def EnsureSession(
        self,
        request: tutor_pb2.EnsureSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> tutor_pb2.StatusResponse:
        creds = request.credentials
        if not creds.email or not creds.password:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "credentials required")
        try:
            session = await resolve_session(
                creds.email,
                creds.password,
                request.project_id,
                request.chat_id,
                request.practice_chat_id,
            )
            return _status_response(session, ready=True, address=self._address)
        except PermissionError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
        except Exception as exc:
            chat_logger.opt(exception=True).error(f"grpc.ensure_session error={exc}")
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def Chat(self, request: tutor_pb2.ChatRequest, context: grpc.aio.ServicerContext) -> AsyncIterator[tutor_pb2.ChatEvent]:
        session = await self._resolve_request_session(request.session, context)
        chat_id = session.practice_chat_id if request.use_practice_chat else session.chat_id
        message = (request.message or "").strip()
        if not message:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "message required")

        try:
            async for event in self._stream_chat(session, chat_id, message):
                yield event
        except Exception as exc:
            chat_logger.opt(exception=True).error(f"grpc.chat error={exc}")
            yield _chat_event("error", error=str(exc))
            yield _chat_event("done")

    async def GeneratePractice(
        self,
        request: tutor_pb2.PracticeRequest,
        context: grpc.aio.ServicerContext,
    ) -> tutor_pb2.PracticeResponse:
        session = await self._resolve_request_session(request.session, context)
        words = [w.strip() for w in request.words if w.strip()]
        if not words:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "words required")
        try:
            result = await generate_practice(session, words, request.level or "B1")
            questions = [
                tutor_pb2.PracticeQuestion(
                    prompt=q["prompt"],
                    options=q["options"],
                    correct_index=q["correct_index"],
                    explanation=q["explanation"],
                )
                for q in result["questions"]
            ]
            return tutor_pb2.PracticeResponse(
                questions=questions,
                source=result.get("source", "repetitor"),
                rag_sources=result.get("rag_sources", []),
            )
        except Exception as exc:
            chat_logger.opt(exception=True).error(f"grpc.generate_practice error={exc}")
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def SearchRag(
        self,
        request: tutor_pb2.RagSearchRequest,
        context: grpc.aio.ServicerContext,
    ) -> tutor_pb2.RagSearchResponse:
        session = await self._resolve_request_session(request.session, context)
        query = (request.query or "").strip()
        if not query:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "query required")
        limit = request.limit or 5

        async with async_session_factory() as db_session:
            if request.corpus == tutor_pb2.RAG_CORPUS_EXAMPLE:
                chunks = await search_examples(db_session, query, session.user_id, limit=limit)
                pb_chunks = [
                    tutor_pb2.RagChunk(
                        id=str(c.example_id),
                        title=c.topic or "",
                        snippet=c.sentence,
                        score=float(c.score),
                    )
                    for c in chunks
                ]
                return tutor_pb2.RagSearchResponse(chunks=pb_chunks)

            if request.corpus == tutor_pb2.RAG_CORPUS_EXPLANATION:
                chunks = await search_explanations(db_session, query, session.user_id, limit=limit)
                pb_chunks = [
                    tutor_pb2.RagChunk(
                        id=str(c.chunk_id),
                        title=c.doc_title or "",
                        snippet=c.content,
                        score=float(c.score),
                    )
                    for c in chunks
                ]
                return tutor_pb2.RagSearchResponse(chunks=pb_chunks)

            chunks = await search(db_session, query, session.user_id, limit=limit)
            context_text = build_context(chunks)
            pb_chunks = [
                tutor_pb2.RagChunk(
                    id=str(c.material_id),
                    title=c.material_name,
                    snippet=c.snippet,
                    score=float(c.score),
                )
                for c in chunks
            ]
            return tutor_pb2.RagSearchResponse(chunks=pb_chunks, context=context_text)

    async def EnrichWord(
        self,
        request: tutor_pb2.EnrichWordRequest,
        context: grpc.aio.ServicerContext,
    ) -> tutor_pb2.EnrichWordResponse:
        session = await self._resolve_request_session(request.session, context)
        word = (request.word or "").strip()
        if not word:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "word required")
        try:
            result = await enrich_word(session, word, request.level or "B1")
            return tutor_pb2.EnrichWordResponse(
                translation=result["translation"],
                example=result["example"],
                transcription=result["transcription"],
                source=result["source"],
            )
        except Exception as exc:
            chat_logger.opt(exception=True).error(f"grpc.enrich_word error={exc}")
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def PublishEvent(
        self,
        request: tutor_pb2.PublishEventRequest,
        context: grpc.aio.ServicerContext,
    ) -> tutor_pb2.PublishEventResponse:
        session = await self._resolve_request_session(request.session, context)
        word = (request.word or "").strip()
        if not word:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "word required")
        try:
            result = await publish_event(
                session,
                word,
                request.correct,
                request.response_time_ms,
                request.attempts,
                request.difficulty,
            )
            return tutor_pb2.PublishEventResponse(accepted=result["accepted"])
        except Exception as exc:
            chat_logger.opt(exception=True).error(f"grpc.publish_event error={exc}")
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def ExplainError(
        self,
        request: tutor_pb2.ExplainErrorRequest,
        context: grpc.aio.ServicerContext,
    ) -> tutor_pb2.ExplainErrorResponse:
        session = await self._resolve_request_session(request.session, context)
        word = (request.word or "").strip()
        if not word:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "word required")
        try:
            result = await explain_error(
                session,
                word,
                request.expected,
                request.got,
                request.sentence,
                self._complete_chat,
            )
            return tutor_pb2.ExplainErrorResponse(
                explanation=result["explanation"],
                source=result["source"],
            )
        except Exception as exc:
            chat_logger.opt(exception=True).error(f"grpc.explain_error error={exc}")
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def GetWeakTopics(
        self,
        request: tutor_pb2.GetWeakTopicsRequest,
        context: grpc.aio.ServicerContext,
    ) -> tutor_pb2.GetWeakTopicsResponse:
        session = await self._resolve_request_session(request.session, context)
        limit = request.limit or 10
        try:
            records = await storage.topic_mastery.get_weak(session.project_id, limit=limit)
            topics = [
                tutor_pb2.WeakTopic(
                    word=r["topic"].removeprefix("word:"),
                    p_know=r["bkt"]["p_know"],
                    als=r["als_score"],
                )
                for r in records
            ]
            return tutor_pb2.GetWeakTopicsResponse(topics=topics)
        except Exception as exc:
            chat_logger.opt(exception=True).error(f"grpc.get_weak_topics error={exc}")
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def _resolve_request_session(
        self,
        proto_session: tutor_pb2.Session,
        context: grpc.aio.ServicerContext,
    ) -> ResolvedSession:
        creds = proto_session.credentials
        if not creds.email or not creds.password:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "credentials required")
        try:
            return await resolve_session(
                creds.email,
                creds.password,
                proto_session.project_id,
                proto_session.chat_id,
                proto_session.practice_chat_id,
            )
        except PermissionError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))

    async def _stream_chat(
        self,
        session: ResolvedSession,
        chat_id: str,
        message: str,
    ) -> AsyncIterator[tutor_pb2.ChatEvent]:
        saved = await save_user_message(chat_id=chat_id, project_id=session.project_id, content=message)
        loaded = await load_context(chat_id=chat_id, project_id=session.project_id)
        runtime = TutorRuntimeContext(
            chat_id=chat_id,
            project_id=session.project_id,
            user_id=UUID(session.user_id),
            history=loaded.history,
            documents_context=loaded.documents_context,
            system_prompt_key=loaded.system_prompt_key,
            include_student_description=loaded.include_student_description,
            project=loaded.project,
            current_user_message=_build_user_message(saved.user_query, saved.user_images),
        )

        full_response = ""
        final_state: dict = {}
        async for event, fs in normalize_agent_events(self._graph, runtime):
            if fs is not None:
                final_state = fs
            if event is None:
                continue
            event_type = getattr(event, "type", "")
            if event_type == "content":
                part = getattr(event, "content", "")
                full_response += part
                yield _chat_event("content", content=part)
            elif event_type == "status":
                yield _chat_event("status", status=getattr(event, "status", ""))
            elif event_type == "error":
                yield _chat_event("error", error=getattr(event, "error", ""))

        if not final_state:
            final_state = {"full_response": full_response}
        elif not final_state.get("full_response"):
            final_state["full_response"] = full_response

        from chat.persistence import save_assistant_message

        await save_assistant_message(runtime, final_state)
        yield _chat_event("done")

    async def _complete_chat(self, session: ResolvedSession, chat_id: str, message: str) -> str:
        parts: list[str] = []
        async for event in self._stream_chat(session, chat_id, message):
            if event.type == "content" and event.content:
                parts.append(event.content)
            if event.type == "error" and event.error:
                raise RuntimeError(event.error)
        text = "".join(parts).strip()
        if not text:
            raise RuntimeError("empty chat response")
        return text
