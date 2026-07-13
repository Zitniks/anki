"""Enhanced logger setup with greppable format and component tags"""

from __future__ import annotations

import sys
from pathlib import Path
from contextvars import ContextVar
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger

from settings import settings

Path(settings.LOGS_PATH).mkdir(parents=True, exist_ok=True)

# Context variable for request ID (set by middleware, used in formatters)
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Get current request ID from context"""
    return request_id_var.get()


def set_request_id(req_id: str) -> None:
    """Set request ID in context"""
    request_id_var.set(req_id)


def console_formatter(record: dict) -> str:
    """Colorized format for console output"""
    extra = record["extra"]
    tag = extra.get("tag", "APP")
    req_id = get_request_id()

    # Build format with colors
    fmt = ("<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
           "<level>{level: <8}</level> | "
           f"<cyan>{tag: <8}</cyan> | ")

    if req_id and req_id != "-":
        fmt += f"<dim>req={req_id}</dim> | "

    fmt += "{message}\n"

    if record["exception"]:
        fmt += "{exception}"

    return fmt


def file_formatter(record: dict) -> str:
    """Plain text format for file output (grep-friendly)"""
    extra = record["extra"]
    tag = extra.get("tag", "APP")
    req_id = get_request_id()

    fmt = ("{time:YYYY-MM-DDTHH:mm:ss.SSSZ} | "
           "{level: <8} | "
           f"{tag: <8} | "
           f"req={req_id} | "
           "{message}\n")

    if record["exception"]:
        fmt += "{exception}"

    return fmt


# Remove default handler
logger.remove()

# Console output (colorized)
logger.add(sys.stdout, format=console_formatter, level=settings.LOG_LEVEL, colorize=True)

# File output (plain text, grep-friendly)
logger.add(
    settings.LOGS_PATH / "app.log",
    format=file_formatter,
    level=settings.LOG_LEVEL,
    rotation=settings.LOGS_ROTATION,
    retention="30 days",
)


def get_logger(tag: str) -> Logger:
    """Get a logger bound to a specific component tag"""
    return logger.bind(tag=tag)


# Pre-bound loggers for each component
startup_logger = get_logger("STARTUP")
chat_logger = get_logger("CHAT")
project_logger = get_logger("PROJECT")
vocab_logger = get_logger("VOCAB")
topic_logger = get_logger("TOPIC")
note_logger = get_logger("NOTE")
lesson_logger = get_logger("LESSON")
material_logger = get_logger("MATERIAL")
llm_logger = get_logger("LLM")
extract_logger = get_logger("EXTRACT")
context_logger = get_logger("CONTEXT")
db_logger = get_logger("DB")
ocr_logger = get_logger("OCR")
doc_logger = get_logger("DOC")
cleanup_logger = get_logger("CLEANUP")
script_logger = get_logger("SCRIPT")
files_logger = get_logger("FILES")
storage_logger = get_logger("STORAGE")
image_gen_logger = get_logger("IMAGE_GEN")
