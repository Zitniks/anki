"""Files router for downloading uploaded files"""

import mimetypes
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from repositories import storage
from routers.dependencies import get_current_user, verify_project_ownership
from logger import files_logger
from typing import Annotated


def content_disposition(disposition: str, filename: str) -> str:
    """Build a Content-Disposition header that handles non-ASCII filenames (RFC 5987)."""
    encoded = quote(filename, safe="")
    return f"{disposition}; filename*=UTF-8''{encoded}"


def _ensure_extension(filename: str, mime_type: str | None) -> str:
    """Append an extension derived from mime_type if filename lacks one.

    Stock photos are persisted with display names like "Photo by X on Pexels"
    that have no extension; without this, downloads and inline-view content
    sniffing both fall back to octet-stream.
    """
    if Path(filename).suffix:
        return filename
    ext = mimetypes.guess_extension(mime_type) if mime_type else None
    return f"{filename}{ext}" if ext else filename


router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.get("")
async def list_all_attachments(current_user: Annotated[dict, Depends(get_current_user)], ) -> list[dict]:
    """Return all uploaded files for the current user's projects."""
    return await storage.files.get_all_with_context(user_id=current_user["id"])


@router.get("/download/{file_id}")
async def download_file(file_id: str,
                        current_user: Annotated[dict, Depends(get_current_user)]) -> Response:
    """Download a file by its ID"""
    try:
        file_record = await storage.files.get(file_id)
        if not file_record:
            files_logger.warning(f"download.not_found file_id={file_id}")
            raise HTTPException(status_code=404, detail="File not found")

        chat = await storage.chats.get(file_record["chat_id"])
        if chat:
            await verify_project_ownership(chat["project_id"], current_user["id"])

        try:
            file_data, mime_type = await storage.file_storage.get_file(file_record["file_path"])
            files_logger.info(
                f"download.success file_id={file_id} filename={file_record['original_filename']} size={len(file_data)}")
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="File not found in storage") from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid file path") from e

        effective_mime = file_record.get("mime_type") or mime_type
        display_name = _ensure_extension(file_record["original_filename"], effective_mime)
        return Response(
            content=file_data,
            media_type=effective_mime,
            headers={
                "Content-Disposition": content_disposition("attachment", display_name),
                "Content-Length": str(len(file_data)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        files_logger.error(f"download.error file_id={file_id} error={e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/view/{file_id}")
async def view_file(file_id: str,
                    current_user: Annotated[dict, Depends(get_current_user)]) -> Response:
    """View a file inline (for images/PDFs) by its ID"""
    try:
        file_record = await storage.files.get(file_id)
        if not file_record:
            files_logger.warning(f"view.not_found file_id={file_id}")
            raise HTTPException(status_code=404, detail="File not found")

        chat = await storage.chats.get(file_record["chat_id"])
        if chat:
            await verify_project_ownership(chat["project_id"], current_user["id"])

        try:
            file_data, mime_type = await storage.file_storage.get_file(file_record["file_path"])
            files_logger.info(f"view.success file_id={file_id} filename={file_record['original_filename']} "
                              f"size={len(file_data)}")
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="File not found in storage") from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid file path") from e

        # DB-stored mime_type is authoritative; the S3-path guess falls back to
        # octet-stream for stored_filenames without an extension (e.g. stock
        # photos whose filename is "Photo by X on Pexels").
        effective_mime = file_record.get("mime_type") or mime_type
        display_name = _ensure_extension(file_record["original_filename"], effective_mime)
        return Response(
            content=file_data,
            media_type=effective_mime,
            headers={
                "Content-Disposition": content_disposition("inline", display_name),
                "Content-Length": str(len(file_data)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        files_logger.error(f"view.error file_id={file_id} error={e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
