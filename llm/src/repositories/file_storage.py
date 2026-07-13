"""File storage repository for uploaded files via S3-compatible object storage."""

import base64
import mimetypes
import os
import uuid
from io import BytesIO
from pathlib import Path

import httpx
from botocore.exceptions import ClientError
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database import FileEntityType
from logger import chat_logger, storage_logger
from repositories.file import FileRepository
from schemas import FileAttachment
from settings import settings

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/aac",
    "audio/m4a",
    "audio/x-m4a",
    "audio/mp4",
    "audio/webm",
    "audio/flac",
}
ALLOWED_MIME_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_DOCUMENT_TYPES | ALLOWED_AUDIO_TYPES


def _get_file_type(mime_type: str) -> str:
    if mime_type in ALLOWED_IMAGE_TYPES:
        return "image"
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        return "docx"
    if mime_type in ALLOWED_AUDIO_TYPES:
        return "audio"
    return "unknown"


def _probe_image_dims(file_data: bytes) -> tuple[int, int] | None:
    """Return (width, height) of an image, or None if probing fails."""
    try:
        with Image.open(BytesIO(file_data)) as im:
            return im.size
    except Exception:
        return None


def _sanitize_filename(filename: str) -> str:
    safe = os.path.basename(filename)
    safe = safe.replace("..", "")
    return safe


def _s3_key(file_path: str) -> str:
    """Build the full S3 object key from a relative file_path."""
    prefix = settings.S3_KEY_PREFIX.rstrip("/")
    return f"{prefix}/{file_path}" if prefix else file_path


def _parse_data_url(data_url: str) -> tuple[bytes, str]:
    """Parse a data URL into ``(bytes, mime_type)``."""
    if not data_url.startswith("data:"):
        raise ValueError("Invalid data URL format")
    metadata, data = data_url.split(",", 1)
    mime_type = metadata.split(";")[0].replace("data:", "")
    return base64.b64decode(data), mime_type


class FileStorageRepository:
    """Repository for file object storage plus file-record persistence helpers."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._files = FileRepository(session_factory)

    def validate_file(
        self,
        file_data: bytes,
        mime_type: str,
        original_filename: str,
    ) -> tuple[bool, str | None]:
        """Validate file before storage."""
        file_size = len(file_data)
        if file_size > MAX_FILE_SIZE:
            return (
                False,
                f"File size ({file_size / 1024 / 1024:.2f}MB) exceeds maximum allowed size (10MB)",
            )
        if file_size == 0:
            return False, "File is empty"
        if mime_type not in ALLOWED_MIME_TYPES:
            return False, f"File type '{mime_type}' is not allowed"
        safe_name = _sanitize_filename(original_filename)
        if not safe_name or safe_name != original_filename:
            return False, "Invalid filename"
        return True, None

    async def save_file(
        self,
        file_data: bytes,
        original_filename: str,
        mime_type: str,
    ) -> tuple[str, str, str, int]:
        """Save a file to S3."""
        is_valid, error_msg = self.validate_file(file_data, mime_type, original_filename)
        if not is_valid:
            raise ValueError(error_msg)

        file_type = _get_file_type(mime_type)
        file_extension = Path(original_filename).suffix or (mimetypes.guess_extension(mime_type) or "")
        stored_filename = f"{uuid.uuid4()}{file_extension}"
        file_size = len(file_data)
        key = _s3_key(stored_filename)

        try:
            async with settings.s3_session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
                await s3.put_object(
                    Bucket=settings.S3_BUCKET,
                    Key=key,
                    Body=file_data,
                    ContentType=mime_type,
                )
            storage_logger.info(f"save.success s3_key={key} filename={original_filename} "
                                f"type={file_type} size={file_size}")
            return stored_filename, stored_filename, file_type, file_size
        except Exception as e:
            storage_logger.error(f"save.error filename={original_filename} error={e}")
            raise OSError(f"Failed to save file to S3: {e}") from e

    async def get_file(self, file_path: str) -> tuple[bytes, str]:
        """Retrieve a file from S3."""
        key = _s3_key(file_path)
        try:
            async with settings.s3_session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
                response = await s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
                file_data = await response["Body"].read()
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(f"File not found in S3: {file_path}") from e
            raise
        mime_type, _ = mimetypes.guess_type(file_path)
        return file_data, mime_type or "application/octet-stream"

    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from S3."""
        key = _s3_key(file_path)
        async with settings.s3_session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
            try:
                await s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
                storage_logger.info(f"delete.success s3_key={key}")
                return True
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    return False
                raise

    async def delete_chat_files(self, chat_id: str) -> int:
        """Delete all files associated with a chat."""
        files = await self._files.get_by_chat(chat_id)
        deleted = 0
        for file_record in files:
            try:
                if await self.delete_file(file_record["file_path"]):
                    deleted += 1
            except Exception as e:
                storage_logger.error(f"delete_chat.error chat_id={chat_id} "
                                     f"file_path={file_record['file_path']} error={e}")
        storage_logger.info(f"delete_chat chat_id={chat_id} count={deleted}")
        return deleted

    async def file_exists(self, file_path: str) -> bool:
        """Return True if the object already exists in S3."""
        key = _s3_key(file_path)
        async with settings.s3_session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
            try:
                await s3.head_object(Bucket=settings.S3_BUCKET, Key=key)
                return True
            except ClientError:
                return False

    async def persist_attachment(
        self,
        attachment: FileAttachment,
        message_id: int,
        chat_id: str,
        extracted_text: str | None = None,
    ) -> int:
        """Save a user attachment to object storage and the files table."""
        file_data, mime_type = _parse_data_url(attachment.dataUrl)
        stored_filename, file_path, file_type, file_size = await self.save_file(
            file_data=file_data,
            original_filename=attachment.name,
            mime_type=mime_type,
        )

        meta: dict | None = None
        if file_type == "image":
            dims = _probe_image_dims(file_data)
            if dims:
                meta = {"width": dims[0], "height": dims[1]}

        file_record = await self._files.create({
            "entity_type": FileEntityType.MESSAGE,
            "entity_id": message_id,
            "chat_id": chat_id,
            "original_filename": attachment.name,
            "stored_filename": stored_filename,
            "file_path": file_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "file_size": file_size,
            "extracted_text": extracted_text,
            "meta": meta,
        })

        chat_logger.info(f"file.save message_id={message_id} filename={attachment.name} "
                         f"type={file_type} size={file_size} has_text={bool(extracted_text)}")
        return file_record["id"]

    async def persist_generated_image(
        self,
        image_url: str,
        message_id: int,
        chat_id: str,
        filename: str | None = None,
        meta: dict | None = None,
    ) -> int:
        """Download a generated or stock image and persist it as a message attachment.

        ``meta`` may carry caller-known fields like ``source``, ``page_url``, ``width``,
        ``height``. Missing width/height are probed from the downloaded bytes.
        """
        filename = filename or "generated_image.png"
        if image_url.startswith("data:"):
            file_data, mime_type = _parse_data_url(image_url)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url)
                file_data = response.content
                mime_type = response.headers.get("content-type", "image/png")

        stored_filename, file_path, file_type, file_size = await self.save_file(
            file_data=file_data,
            original_filename=filename,
            mime_type=mime_type,
        )

        merged_meta: dict = dict(meta or {})
        if "width" not in merged_meta or "height" not in merged_meta:
            dims = _probe_image_dims(file_data)
            if dims:
                merged_meta.setdefault("width", dims[0])
                merged_meta.setdefault("height", dims[1])

        file_record = await self._files.create({
            "entity_type": FileEntityType.MESSAGE,
            "entity_id": message_id,
            "chat_id": chat_id,
            "original_filename": filename,
            "stored_filename": stored_filename,
            "file_path": file_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "file_size": file_size,
            "extracted_text": None,
            "meta": merged_meta or None,
        })

        chat_logger.info(f"image.save_generated message_id={message_id} file_id={file_record['id']} "
                         f"filename={filename} size={file_size}")
        return file_record["id"]
