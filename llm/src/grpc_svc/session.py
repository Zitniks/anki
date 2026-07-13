"""Session bootstrap for gRPC callers (Anki service)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from routers.dependencies import verify_password
from repositories import storage


@dataclass
class ResolvedSession:
    user_id: str
    project_id: str
    chat_id: str
    practice_chat_id: str


async def authenticate(email: str, password: str) -> dict:
    user = await storage.users.get_by_email(email)
    hashed = await storage.users.get_hashed_password(email)
    if not user or not hashed or not verify_password(password, hashed):
        raise PermissionError("invalid credentials")
    if not user["is_active"]:
        raise PermissionError("account inactive")
    return user


async def ensure_project(user_id: str, project_id: str | None) -> str:
    if project_id:
        project = await storage.projects.get(project_id)
        if project and project["user_id"] == user_id:
            return project_id

    projects = await storage.projects.get_all(user_id=user_id)
    for project in projects:
        if project.get("name") == "Anki Lite":
            return project["id"]
    if projects:
        return projects[0]["id"]

    new_id = str(uuid.uuid4())
    await storage.projects.create({
        "id": new_id,
        "user_id": user_id,
        "name": "Anki Lite",
        "student_name": "Self",
        "student_level": "B1",
        "description": "Vocabulary practice via Anki Lite",
        "notes": None,
    })
    await storage.chats.create({"id": str(uuid.uuid4()), "project_id": new_id, "name": "Anki Tutor"})
    return new_id


async def ensure_chat(project_id: str, chat_id: str | None, name: str) -> str:
    if chat_id:
        chat = await storage.chats.get(chat_id)
        if chat and chat["project_id"] == project_id:
            return chat_id

    chats = await storage.chats.get_by_project(project_id)
    for chat in chats:
        if chat.get("name") == name:
            return chat["id"]

    new_id = str(uuid.uuid4())
    await storage.chats.create({"id": new_id, "project_id": project_id, "name": name})
    return new_id


async def resolve_session(
    email: str,
    password: str,
    project_id: str = "",
    chat_id: str = "",
    practice_chat_id: str = "",
) -> ResolvedSession:
    user = await authenticate(email, password)
    pid = await ensure_project(user["id"], project_id or None)
    cid = await ensure_chat(pid, chat_id or None, "Anki Tutor")
    pcid = await ensure_chat(pid, practice_chat_id or None, "Anki Practice")
    return ResolvedSession(
        user_id=user["id"],
        project_id=pid,
        chat_id=cid,
        practice_chat_id=pcid,
    )
