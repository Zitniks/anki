"""Router for repeat items"""

from datetime import datetime
from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import Response
from urllib.parse import quote

from database import FileEntityType
from schemas import RepeatItemCreate, RepeatItemUpdate
from repositories import storage
from routers.dependencies import get_current_user, get_project_or_404, verify_project_ownership
from logger import db_logger
import contextlib

router = APIRouter(prefix="/api/v1/repeat-items", tags=["repeat-items"])


@router.post("/{project_id}")
async def create_repeat_item(item_data: RepeatItemCreate,
                             project: Annotated[dict, Depends(get_project_or_404)]) -> dict[str, Any]:
    """Create a new repeat item for a project"""
    data = dict(item_data)
    data["project_id"] = project["id"]
    item = await storage.repeat_items.create(data=data)
    db_logger.info(f"repeat_item.create item={item}")
    return {"item": item}


@router.get("/{project_id}")
async def list_repeat_items(project: Annotated[dict, Depends(get_project_or_404)], ) -> dict[str, Any]:
    """Get all repeat items for a project"""
    items = await storage.repeat_items.get_by_project(project_id=project["id"])
    db_logger.info(f"repeat_item.list project_id={project['id']} count={len(items)}")
    return {"items": items}


@router.patch("/{item_id}")
async def update_repeat_item(item_id: int,
                             item_data: RepeatItemUpdate,
                             current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Update a repeat item"""
    item = await storage.repeat_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Repeat item not found")

    await verify_project_ownership(item["project_id"], current_user["id"])

    data = item_data.model_dump(exclude_unset=True)
    if data.get("status") == "done":
        data["done_at"] = datetime.utcnow()
    elif data.get("status") and data["status"] != "done":
        data["done_at"] = None

    updated = await storage.repeat_items.update(item_id=item_id, data=data)
    db_logger.info(f"repeat_item.update item={updated}")
    return {"item": updated}


@router.delete("/{item_id}")
async def delete_repeat_item(item_id: int,
                             current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete a repeat item"""
    item = await storage.repeat_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Repeat item not found")

    await verify_project_ownership(item["project_id"], current_user["id"])
    await storage.repeat_items.delete(item_id)
    db_logger.info(f"repeat_item.delete item_id={item_id}")
    return {"status": "deleted"}


@router.post("/{item_id}/files")
async def upload_repeat_item_file(item_id: int,
                                  file: Annotated[UploadFile, File()],
                                  current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Upload a file and attach it to a repeat item"""
    item = await storage.repeat_items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Repeat item not found")

    await verify_project_ownership(item["project_id"], current_user["id"])

    file_data = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    original_filename = file.filename or "upload"

    try:
        stored_filename, file_path, file_type, file_size = await storage.file_storage.save_file(
            file_data=file_data,
            original_filename=original_filename,
            mime_type=mime_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail="Failed to save file") from e

    record = await storage.files.create(
        data={
            "entity_type": FileEntityType.REPEAT_ITEM,
            "entity_id": item_id,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "file_path": file_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "file_size": file_size,
        })

    db_logger.info(f"repeat_item_file.upload item_id={item_id} filename={original_filename}")
    return {"file": record}


@router.get("/files/view/{file_id}")
async def view_repeat_item_file(file_id: str,
                                current_user: Annotated[dict, Depends(get_current_user)]) -> Response:
    """View a repeat item file inline"""
    record = await storage.files.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    item = await storage.repeat_items.get(record["entity_id"])
    if item:
        await verify_project_ownership(item["project_id"], current_user["id"])

    try:
        file_data, mime_type = await storage.file_storage.get_file(record["file_path"])
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="File not found in storage") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid file path") from e

    encoded = quote(record["original_filename"], safe="")
    return Response(
        content=file_data,
        media_type=mime_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded}"},
    )


@router.delete("/files/{file_id}")
async def delete_repeat_item_file(file_id: str,
                                  current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete an attached file from a repeat item"""
    record = await storage.files.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    item = await storage.repeat_items.get(record["entity_id"])
    if item:
        await verify_project_ownership(item["project_id"], current_user["id"])

    with contextlib.suppress(FileNotFoundError, ValueError):
        await storage.file_storage.delete_file(record["file_path"])

    await storage.files.delete(file_id)
    db_logger.info(f"repeat_item_file.delete file_id={file_id}")
    return {"status": "deleted"}
