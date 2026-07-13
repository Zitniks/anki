"""Authentication router: register, login, logout, me"""

import uuid
from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, Depends, Response

from schemas import UserCreate, UserLogin, UserResponse
from repositories import storage
from routers.dependencies import get_current_user, hash_password, verify_password, create_access_token
from settings import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_COOKIE_NAME = "access_token"
_COOKIE_MAX_AGE = settings.JWT_EXPIRE_MINUTES * 60


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.get("/registration-enabled")
async def registration_enabled() -> dict[str, bool]:
    return {"enabled": settings.REGISTRATION_ENABLED}


@router.post("/register")
async def register(data: UserCreate, response: Response) -> dict[str, Any]:
    if not settings.REGISTRATION_ENABLED:
        raise HTTPException(status_code=403, detail="Registration is currently disabled")

    existing = await storage.users.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = await storage.users.create({
        "id": uuid.uuid4(),
        "email": data.email,
        "hashed_password": hash_password(data.password),
    })
    _set_auth_cookie(response, create_access_token(user["id"]))
    return {"ok": True}


@router.post("/login")
async def login(data: UserLogin, response: Response) -> dict[str, Any]:
    user = await storage.users.get_by_email(data.email)
    hashed = await storage.users.get_hashed_password(data.email)
    if not user or not hashed or not verify_password(data.password, hashed):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    _set_auth_cookie(response, create_access_token(user["id"]))
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[dict, Depends(get_current_user)]) -> Any:
    return current_user
