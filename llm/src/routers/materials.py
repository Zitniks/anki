"""Materials API router"""

from typing import Any, Annotated

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import Response
from urllib.parse import quote

from database import FileEntityType
from schemas import MaterialData, MaterialLinkData
from repositories import storage
from routers.dependencies import get_current_user, get_material_or_404
from logger import material_logger
from file_processing import extract_pdf_text, extract_docx_text
from analytics.rag import index_material
from database import async_session_factory
import contextlib

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.post("/")
async def create_material(data: MaterialData,
                          current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Create a new material"""
    material_data = dict(data)
    material_data["user_id"] = current_user["id"]
    material = await storage.materials.create(data=material_data)

    with contextlib.suppress(Exception):
        async with async_session_factory() as session:
            await index_material(
                session,
                material["id"],
                material.get("name", ""),
                material.get("content", "") or "",
                material.get("tags"),
            )

    material_logger.info(f"material.create material={material}")
    return {"material": material}


@router.get("/")
async def read_materials(current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get all materials for the current user"""
    materials = await storage.materials.get_all(user_id=current_user["id"])

    material_logger.info(f"material.list count={len(materials)}")
    return {"materials": materials}


@router.get("/{material_id}")
async def read_material(material: Annotated[dict, Depends(get_material_or_404)]) -> dict[str, Any]:
    """Get a specific material"""
    material_logger.info(f"material.read material_id={material['id']}")
    return {"material": material}


@router.patch("/{material_id}")
async def update_material(data: MaterialData,
                          material: Annotated[dict, Depends(get_material_or_404)]) -> dict[str, Any]:
    """Update a material"""
    updated = await storage.materials.update(material_id=int(material["id"]), data=dict(data))

    with contextlib.suppress(Exception):
        async with async_session_factory() as session:
            await index_material(
                session,
                updated["id"],
                updated.get("name", ""),
                updated.get("content", "") or "",
                updated.get("tags"),
            )

    material_logger.info(f"material.update material_id={material['id']} data={dict(data)}")
    return {"material": updated}


@router.delete("/{material_id}")
async def delete_material(material: Annotated[dict, Depends(get_material_or_404)], ) -> dict[str, Any]:
    """Delete a material"""
    # Delete associated files from object storage
    for file_record in material.get("files", []):
        with contextlib.suppress(FileNotFoundError, ValueError):
            await storage.file_storage.delete_file(file_record["file_path"])

    await storage.materials.delete(int(material["id"]))
    material_logger.info(f"material.delete material_id={material['id']}")
    return {"status": "deleted"}


# ── File attachments ──


@router.post("/{material_id}/files")
async def upload_material_file(file: Annotated[UploadFile, File()],
                               material: Annotated[dict, Depends(get_material_or_404)]) -> dict[str, Any]:
    """Upload a file and attach it to a material"""
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
            "entity_type": FileEntityType.MATERIAL,
            "entity_id": material["id"],
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "file_path": file_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "file_size": file_size,
        })

    # Extract text and append to material content so it's indexed in FTS (content_tsv)
    extracted = ""
    lower_name = original_filename.lower()
    with contextlib.suppress(Exception):
        if lower_name.endswith(".pdf"):
            extracted, _ = await extract_pdf_text(file_data, original_filename)
        elif lower_name.endswith(".docx"):
            extracted, _ = await extract_docx_text(file_data, original_filename)

    if extracted.strip():
        existing_content = material.get("content") or ""
        separator = "\n\n--- Extracted from file ---\n" if existing_content else ""
        await storage.materials.update(
            material["id"],
            {"content": existing_content + separator + extracted[:8000]},
        )
        material_logger.info(
            f"material_file.fts_indexed material_id={material['id']} "
            f"filename={original_filename} chars={len(extracted)}"
        )

    material_logger.info(f"material_file.upload material_id={material['id']} filename={original_filename}")
    return {"file": record}


@router.get("/files/view/{file_id}")
async def view_material_file(file_id: str,
                             current_user: Annotated[dict, Depends(get_current_user)]) -> Response:
    """View a material file inline"""
    record = await storage.files.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    material = await storage.materials.get(record["entity_id"])
    if not material or material["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="File not found")

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
async def delete_material_file(file_id: str,
                               current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete an attached file from a material"""
    record = await storage.files.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    material = await storage.materials.get(record["entity_id"])
    if not material or material["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="File not found")

    with contextlib.suppress(FileNotFoundError, ValueError):
        await storage.file_storage.delete_file(record["file_path"])

    await storage.files.delete(file_id)
    material_logger.info(f"material_file.delete file_id={file_id}")
    return {"status": "deleted"}


# ── Link attachments ──


@router.post("/{material_id}/links")
async def add_material_link(data: MaterialLinkData,
                            material: Annotated[dict, Depends(get_material_or_404)]) -> dict[str, Any]:
    """Add a link to a material"""
    record = await storage.material_links.create(data={
        "material_id": material["id"],
        "url": data.url,
        "name": data.name,
    })

    material_logger.info(f"material_link.create material_id={material['id']} url={data.url}")
    return {"link": record}


@router.delete("/links/{link_id}")
async def delete_material_link(link_id: int,
                               current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Delete a link from a material"""
    record = await storage.material_links.get(link_id)
    if not record:
        raise HTTPException(status_code=404, detail="Link not found")

    material = await storage.materials.get(record["material_id"])
    if not material or material["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Link not found")

    await storage.material_links.delete(link_id)
    material_logger.info(f"material_link.delete link_id={link_id}")
    return {"status": "deleted"}
