"""User repository"""

from sqlalchemy import select

from database import User
from repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> dict | None:
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            return user.to_dict() if user else None

    async def get_hashed_password(self, email: str) -> str | None:
        """Return hashed_password for the given email (not exposed via to_dict)."""
        async with self._session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            return user.hashed_password if user else None
