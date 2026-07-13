"""Idempotent seed for the service account ankis authenticates as over gRPC
(REPETITOR_EMAIL/REPETITOR_PASSWORD on the ankis side, ADMIN_EMAIL/ADMIN_PASSWORD
here). Safe to run on every deploy: no-ops if the user already exists.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select

from database import async_session_factory, User
from routers.dependencies import hash_password
from settings import settings


async def main() -> None:
    async with async_session_factory() as session:
        existing = await session.scalar(select(User).where(User.email == settings.ADMIN_EMAIL))
        if existing:
            print(f"seed_admin: user {settings.ADMIN_EMAIL} already exists, skipping")
            return

        user = User(email=settings.ADMIN_EMAIL, hashed_password=hash_password(settings.ADMIN_PASSWORD))
        session.add(user)
        await session.commit()
        print(f"seed_admin: created user {settings.ADMIN_EMAIL}")


if __name__ == "__main__":
    asyncio.run(main())
