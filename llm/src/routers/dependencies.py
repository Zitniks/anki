"""FastAPI dependencies for authentication and ownership checks"""

from datetime import datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from fastapi import HTTPException, Request

from repositories import storage
from settings import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """
    Decode JWT and return the user ID.

    Parameters
    ----------
    token : str
        Encoded JWT access token.

    Returns
    -------
    str or None
        User ID (``sub`` claim) on success, or None if invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


async def get_current_user(request: Request) -> dict:
    """Extract and validate JWT from HttpOnly cookie. Returns user dict."""
    token = request.cookies.get("access_token", "")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await storage.users.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    return user


async def get_project_or_404(project_id: str, request: Request) -> dict:
    """Dependency: load project by path param and verify ownership. Returns project dict.

    Raises 404 both when the project is missing and when it belongs to another user,
    so the response does not leak the existence of ids the caller cannot access.
    """
    current_user = await get_current_user(request)

    project = await storage.projects.get(project_id)
    if not project or project["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


async def get_material_or_404(material_id: int, request: Request) -> dict:
    """Dependency: load material by path param and verify ownership. Returns material dict.

    Raises 404 both when the material is missing and when it belongs to another user.
    """
    current_user = await get_current_user(request)

    material = await storage.materials.get(material_id)
    if not material or material["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Material not found")

    return material


async def verify_project_ownership(project_id: str, user_id: str) -> None:
    """Helper: verify user owns a project. Used when project_id comes from a loaded entity.

    Raises 404 in both the missing and not-owned cases, to avoid leaking which
    project ids exist.
    """
    project = await storage.projects.get(project_id)
    if not project or project["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
