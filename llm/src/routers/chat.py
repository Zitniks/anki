"""Chat API router with LangGraph integration"""
import uuid
from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from langchain_core.prompts import ChatPromptTemplate

from schemas import ChatRequest, ChatCreate, ChatSettingsUpdate
from repositories import storage
from langgraph.graph.state import CompiledStateGraph

from chat.lifecycle import get_graph, handle_chat
from chat.prompts import SYSTEM_PROMPTS
from routers.dependencies import get_current_user, get_project_or_404, verify_project_ownership
from logger import chat_logger
from settings import settings

router = APIRouter(prefix="/api/v1", tags=["chat"])

CHAT_GENERATION_SYSTEM_PROMPT = """
Ты генерируешь СТРОГО ОДНО короткое и ёмкое название для чата.
ВАЖНЫЕ ПРАВИЛА:
- 2–4 слова
- Никакой пунктуации
- Никаких кавычек
- Используй как русский так и английский язык в зависимости от контекста
""".strip()

# ========== ROUTES ==========


@router.post("/chats/{chat_id}/messages/stream")
async def chat_stream(chat_id: str,
                      request: ChatRequest,
                      current_user: Annotated[dict, Depends(get_current_user)],
                      graph: Annotated[CompiledStateGraph, Depends(get_graph)]) -> StreamingResponse:
    """Send message to chat with streaming response"""
    chat = await storage.chats.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await verify_project_ownership(chat["project_id"], current_user["id"])
    project_id = chat["project_id"]

    try:
        return await handle_chat(
            chat_id=chat_id,
            project_id=project_id,
            user_id=current_user["id"],
            request=request,
            graph=graph,
        )
    except HTTPException:
        raise
    except Exception as e:
        chat_logger.opt(exception=True).error(f"api.stream_error project_id={project_id} chat_id={chat_id} error={e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str,
                   current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get chat information"""
    chat = await storage.chats.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await verify_project_ownership(chat["project_id"], current_user["id"])

    messages = await storage.messages.get_by_chat(chat_id)
    chat_files = await storage.files.get_by_chat(chat_id)
    files_by_message = {}
    for file in chat_files:
        message_id = file["entity_id"]
        if message_id not in files_by_message:
            files_by_message[message_id] = []
        files_by_message[message_id].append(file)

    for message in messages:
        message["files"] = files_by_message.get(message["id"], [])

    return {"chat": chat, "messages": messages}


@router.post("/chats/{chat_id}/generate-name")
async def generate_chat_name(chat_id: str,
                             current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Generate chat name based on conversation"""
    chat = await storage.chats.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await verify_project_ownership(chat["project_id"], current_user["id"])

    messages = await storage.messages.get_by_chat(chat_id)
    if not messages:
        raise HTTPException(status_code=400, detail="Cannot generate name for empty chat")

    conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    prompt = ChatPromptTemplate.from_messages([
        ("system", CHAT_GENERATION_SYSTEM_PROMPT),
        ("human", "Разговор:\n{conversation}")
    ])

    chain = prompt | settings.llm_cheap
    answer = await chain.ainvoke({"conversation": conversation})
    generated_name = answer.content
    chat_logger.info(f"chat.name_generated chat_id={chat_id} name={generated_name}")

    await storage.chats.update(chat_id=chat_id, data={"name": generated_name})
    return {"generated_name": generated_name}


@router.post("/projects/{project_id}/chats")
async def create_chat(request: ChatCreate,
                      project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Create new chat in project"""
    try:
        chat = await storage.chats.create({
            "id": str(uuid.uuid4()),
            "project_id": project["id"],
            "name": request.name
        })
        chat_logger.info(f"chat.create project_id={project['id']} chat_id={chat['id']}")
        return {"chat": chat}

    except Exception as e:
        chat_logger.opt(exception=True).error(f"chat.create_error project_id={project['id']} error={e}")
        raise HTTPException(status_code=500, detail="Error creating chat") from e


@router.patch("/chats/{chat_id}")
async def update_chat(chat_id: str,
                      request: ChatCreate,
                      current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Update chat name"""
    chat = await storage.chats.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await verify_project_ownership(chat["project_id"], current_user["id"])

    try:
        updated_chat = await storage.chats.update(chat_id=chat_id, data={"name": request.name})
        return {"chat": updated_chat}
    except Exception as e:
        chat_logger.opt(exception=True).error(f"chat.update_error chat_id={chat_id} error={e}")
        raise HTTPException(status_code=500, detail="Error updating chat") from e


@router.patch("/chats/{chat_id}/settings")
async def update_chat_settings(chat_id: str,
                               request: ChatSettingsUpdate,
                               current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Update per-chat settings (e.g. whether to include student description in LLM prompt)."""
    chat = await storage.chats.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await verify_project_ownership(chat["project_id"], current_user["id"])

    try:
        updated_chat = await storage.chats.update(
            chat_id=chat_id,
            data={
                "include_student_description": request.include_student_description,
                "system_prompt_key": request.system_prompt_key,
            },
        )
        return {"chat": updated_chat}
    except Exception as e:
        chat_logger.opt(exception=True).error(f"chat.settings_update_error chat_id={chat_id} error={e}")
        raise HTTPException(status_code=500, detail="Error updating chat settings") from e


@router.get("/system-prompts")
async def list_system_prompts(current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Return available system prompt options for the chat settings dropdown."""
    return {"prompts": [{"key": k, "label": v.label} for k, v in SYSTEM_PROMPTS.items()]}


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str,
                      current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete chat"""
    chat = await storage.chats.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await verify_project_ownership(chat["project_id"], current_user["id"])

    try:
        await storage.chats.delete(chat_id)
        chat_logger.info(f"chat.delete chat_id={chat_id}")
        return {"status": "deleted"}
    except Exception as e:
        chat_logger.opt(exception=True).error(f"chat.delete_error chat_id={chat_id} error={e}")
        raise HTTPException(status_code=500, detail="Error deleting chat") from e


@router.get("/projects/{project_id}/chats")
async def get_project_chats(project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Get all project chats"""
    try:
        chats = await storage.chats.get_by_project(project["id"])
        return {"chats": chats}
    except Exception as e:
        chat_logger.opt(exception=True).error(f"chat.list_error project_id={project['id']} error={e}")
        raise HTTPException(status_code=500, detail="Error getting chats") from e
