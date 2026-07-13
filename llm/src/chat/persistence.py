"""Chat persistence: load conversation state, save user/assistant messages.

Thin adapter over ``repositories.storage`` + ``storage.file_storage`` scoped to
the chat turn lifecycle. Reads and writes live together because they share
helpers (file references, document context) and never call each other.
"""

import base64
from collections import defaultdict
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from chat.state import TutorRuntimeContext
from file_processing import detect_attachment_type, process_multiple_documents
from logger import chat_logger, context_logger
from repositories import storage
from schemas import (
    AttachmentType,
    FileAttachment,
    ProjectContext,
)

_STOCK_PHOTO_FILENAME_SUFFIX = " on Pexels"

# ========== TURN-LOCAL MODELS ==========


class SavedUserMessage(BaseModel):
    """Outputs from ``save_user_message`` — values needed downstream in the request."""

    message_id: int
    user_query: str
    user_images: list[dict] = Field(default_factory=list)
    has_large_document: bool = False


class LoadedContext(BaseModel):
    """Outputs from ``load_context`` — conversation state loaded for this turn."""

    model_config = {"arbitrary_types_allowed": True}

    history: list[dict] = Field(default_factory=list)
    project: ProjectContext
    documents_context: str = "Документы не загружены."
    include_student_description: bool = True
    system_prompt_key: str = "default"


# ========== WRITES ==========


async def save_user_message(
    chat_id: str,
    project_id: str,
    content: str,
    attachments: list[FileAttachment] | None = None,
) -> SavedUserMessage:
    """Persist the user message and its attachments.

    Extracts text from document attachments, saves the message row, writes
    every attachment to storage.

    Parameters
    ----------
    chat_id : str
        Chat ID.
    project_id : str
        Project ID.
    content : str
        User message text.
    attachments : list of FileAttachment, optional
        Message attachments.

    Returns
    -------
    SavedUserMessage
        message_id, llm-facing user_query, user_images, has_large_document flag.
    """
    file_extractions: dict[str, str] = {}
    has_large_document = False

    if attachments:
        documents = [
            att for att in attachments if detect_attachment_type(att.name, att.dataUrl) != AttachmentType.IMAGE
        ]
        if documents:
            chat_logger.info(f"doc.start project_id={project_id} chat_id={chat_id} count={len(documents)}")
            doc_results, has_large_document = await process_multiple_documents(documents)
            for doc, doc_text in doc_results:
                if doc_text:
                    file_extractions[doc.name] = doc_text

    saved_message = await storage.messages.create({
        "project_id": project_id,
        "chat_id": chat_id,
        "role": "user",
        "content": content,
        "token_count": 0,
    })
    message_id = saved_message["id"]

    chat_logger.info(f"message.save_user project_id={project_id} chat_id={chat_id} "
                     f"message_id={message_id} content_len={len(content)} "
                     f"attachments={len(attachments) if attachments else 0}")

    if attachments:
        for att in attachments:
            try:
                await storage.file_storage.persist_attachment(
                    att,
                    message_id=message_id,
                    chat_id=chat_id,
                    extracted_text=file_extractions.get(att.name),
                )
            except Exception as e:
                chat_logger.error(f"file.save_error message_id={message_id} filename={att.name} error={e}")

    # Build LLM-facing user query: original text + short file references.
    # Full document text lives in LoadedContext.documents_context (loaded separately).
    llm_query = content
    refs = [f"[Загружен файл: {fn}]" for fn, text in file_extractions.items() if text]
    if refs:
        llm_query = (llm_query + "\n" + "\n".join(refs)) if llm_query else "\n".join(refs)

    user_images = []
    if attachments:
        user_images = [
            {"name": att.name, "url": att.dataUrl}
            for att in attachments
            if detect_attachment_type(att.name, att.dataUrl) == AttachmentType.IMAGE
        ]

    return SavedUserMessage(
        message_id=message_id,
        user_query=llm_query,
        user_images=user_images,
        has_large_document=has_large_document,
    )


async def save_assistant_message(
    runtime_context: TutorRuntimeContext,
    final_state: dict,
) -> dict:
    """Persist the assistant message, any attached images, and vocabulary.

    Reads ``final_state["full_response"]``, ``thinking_blocks``, ``images``
    (list of ``{name, url, source, ...}``), ``output_tokens`` and writes them
    to storage. Mutates each entry in ``final_state["images"]`` by replacing
    its ``url`` with the local view URL.
    """
    full_response = final_state.get("full_response", "")
    thinking_blocks = final_state.get("thinking_blocks", [])
    images = final_state.get("images", [])
    output_tokens = final_state.get("output_tokens", 0)

    saved_message = await storage.messages.create({
        "project_id": runtime_context.project_id,
        "chat_id": runtime_context.chat_id,
        "role": "assistant",
        "content": full_response,
        "thinking_blocks": thinking_blocks,
        "token_count": output_tokens,
    })
    message_id = saved_message["id"]

    chat_logger.info(f"message.save_assistant project_id={runtime_context.project_id} "
                     f"chat_id={runtime_context.chat_id} "
                     f"message_id={message_id} content_len={len(full_response)} "
                     f"thinking_blocks={len(thinking_blocks)} "
                     f"images={len(images)}")

    file_ids: list[int] = []
    for img in images:
        try:
            meta = {
                k: img[k]
                for k in ("width", "height", "source", "page_url")
                if k in img and img[k] is not None
            }
            file_id = await storage.file_storage.persist_generated_image(
                img["url"],
                message_id=message_id,
                chat_id=runtime_context.chat_id,
                filename=img.get("name"),
                meta=meta or None,
            )
            img["url"] = f"/api/v1/files/view/{file_id}"
            file_ids.append(file_id)
        except Exception as e:
            chat_logger.error(f"image.save_error message_id={message_id} error={e}")
    if file_ids:
        saved_message["generated_image_file_ids"] = file_ids

    await storage.chats.update(runtime_context.chat_id, {"updated_at": datetime.utcnow().isoformat()})

    return saved_message


# ========== READS ==========


async def load_context(chat_id: str, project_id: str) -> LoadedContext:
    """Load history, project data, and documents context for the turn."""
    project = await _load_project(project_id)

    chat = await storage.chats.get(chat_id)
    include_student_description = chat.get("include_student_description", True) if chat else True
    system_prompt_key = chat.get("system_prompt_key", "default") if chat else "default"

    all_messages = await storage.messages.get_by_chat(chat_id)
    if not all_messages:
        return LoadedContext(
            history=[],
            project=project,
            documents_context="Документы не загружены.",
            include_student_description=include_student_description,
            system_prompt_key=system_prompt_key,
        )

    all_files = await storage.files.get_by_chat(chat_id)
    documents_context = _build_documents_context(all_files)
    history = await _add_file_references(all_messages, all_files)

    context_logger.info(f"context.load chat_id={chat_id} messages={len(history)}")

    return LoadedContext(
        history=history,
        project=project,
        documents_context=documents_context,
        include_student_description=include_student_description,
        system_prompt_key=system_prompt_key,
    )


def convert_to_langchain_messages(messages: list[dict]) -> list:
    """Convert persisted message dicts to LangChain message objects."""
    result = []
    for msg in messages:
        if msg["role"] == "user":
            images = msg.get("images")
            if images:
                content = [{"type": "text", "text": msg["content"]}]
                for img in images:
                    content.append({"type": "image_url", "image_url": {"url": img["url"]}})
                result.append(HumanMessage(content=content))
            else:
                result.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            result.append(AIMessage(content=msg["content"]))
            # Provider rejects image blocks inside AIMessage; reintroduce
            # AI-generated images as a synthetic user turn so the LLM can see
            # them when iterating ("change day to night", recolor, etc.).
            images = msg.get("images")
            if images:
                content: list[dict] = [{"type": "text", "text": "[Сгенерированное ранее изображение]"}]
                for img in images:
                    content.append({"type": "image_url", "image_url": {"url": img["url"]}})
                result.append(HumanMessage(content=content))
    return result


async def _load_project(project_id: str) -> ProjectContext:
    """Load project data for the LLM prompt."""
    project = await storage.projects.get(project_id)
    if not project:
        context_logger.warning(f"context.project_not_found project_id={project_id}")
        return ProjectContext(
            student_name="Unknown",
            student_level="Unknown",
            description="не указано",
            existing_vocabulary=[],
            existing_topics=[],
        )

    vocabulary = await storage.vocabulary.get_active_by_project(project_id)
    topics = await storage.topics.get_by_project(project_id)

    return ProjectContext(
        student_name=project["student_name"],
        student_level=project["student_level"],
        description=project.get("description", "не указано"),
        existing_vocabulary=[v["word"] for v in vocabulary],
        existing_topics=[t["topic"] for t in topics if t["status"] == "DONE"],
    )


def _build_documents_context(all_files: list[dict]) -> str:
    """Build a standalone document context block for the system prompt."""
    doc_files = [f for f in all_files if f.get("extracted_text") and f.get("file_type") in ("pdf", "docx", "audio")]
    if not doc_files:
        return "Документы не загружены."

    entries = [f"--- {f['original_filename']} ---\n{f['extracted_text']}" for f in doc_files]
    return "\n\n".join(entries)


async def _add_file_references(messages: list[dict], all_files: list[dict]) -> list[dict]:
    """Attach file references to messages: text tags for docs, inline base64 for images."""
    if not all_files:
        return messages

    files_by_message = defaultdict(list)
    for file in all_files:
        files_by_message[file["entity_id"]].append(file)

    for msg in messages:
        files = files_by_message.get(msg["id"], [])
        if not files:
            continue

        refs = [f"[Загружен файл: {f['original_filename']}]" for f in files if f["file_type"] != "image"]
        if refs:
            msg["content"] = msg["content"] + "\n" + "\n".join(refs)

        image_files = [
            f for f in files
            if f["file_type"] == "image" and not f["original_filename"].endswith(_STOCK_PHOTO_FILENAME_SUFFIX)
        ]
        if image_files:
            msg["images"] = []
            for f in image_files:
                try:
                    file_data, mime_type = await storage.file_storage.get_file(f["file_path"])
                    data_url = f"data:{mime_type};base64,{base64.b64encode(file_data).decode()}"
                    img_entry = {"name": f["original_filename"], "url": data_url}
                    meta = f.get("meta") or {}
                    if meta.get("width") and meta.get("height"):
                        img_entry["width"] = meta["width"]
                        img_entry["height"] = meta["height"]
                    msg["images"].append(img_entry)
                except Exception as e:
                    context_logger.warning(f"context.image_load_error file={f['original_filename']} error={e}")

    return messages
