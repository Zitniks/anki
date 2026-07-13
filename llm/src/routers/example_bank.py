"""Example bank API router (Example RAG corpus)"""

import contextlib
from typing import Any, Annotated

from fastapi import APIRouter, Depends

from schemas import ExampleData
from repositories import storage
from routers.dependencies import get_current_user
from logger import material_logger
from analytics.example_bank import index_example
from database import async_session_factory

router = APIRouter(prefix="/api/v1/example-bank", tags=["example-bank"])


@router.post("/")
async def create_example(
    data: ExampleData,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    """Create a new example sentence and index it for Example RAG."""
    example_data = dict(data)
    example_data["user_id"] = current_user["id"]
    example = await storage.example_bank.create(data=example_data)

    with contextlib.suppress(Exception):
        async with async_session_factory() as session:
            await index_example(session, example["id"], example["sentence"], example["topic"])

    material_logger.info(f"example_bank.create example={example}")
    return {"example": example}


@router.get("/")
async def read_examples(current_user: Annotated[dict, Depends(get_current_user)]) -> dict[str, Any]:
    """Get all example sentences for the current user."""
    examples = await storage.example_bank.get_all(user_id=current_user["id"])

    material_logger.info(f"example_bank.list count={len(examples)}")
    return {"examples": examples}
