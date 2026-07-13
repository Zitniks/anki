"""UsageLog repository"""

from datetime import datetime, timedelta

from sqlalchemy import func, and_, select

from database import UsageLog
from repositories.base import BaseRepository


class UsageLogRepository(BaseRepository[UsageLog]):
    model = UsageLog

    async def get_daily_tokens(self, user_id: str) -> int:
        """Sum of input+output tokens for user today (UTC).

        Parameters
        ----------
        user_id : str
            User UUID as string.

        Returns
        -------
        int
            Total tokens consumed today.
        """
        today = datetime.utcnow().date()
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(UsageLog.input_tokens + UsageLog.output_tokens), 0))
                .where(and_(
                    UsageLog.user_id == user_id,
                    func.date(UsageLog.created_at) == today
                ))
            )
            return result.scalar_one()

    async def get_window_summary(self, user_id: str, days: int) -> dict:
        """Per-day breakdown + totals over the last ``days`` days (UTC, inclusive of today).

        Parameters
        ----------
        user_id : str
            User UUID as string.
        days : int
            Number of trailing days to include (must be >= 1).

        Returns
        -------
        dict
            ``{"by_day": [{"date": "YYYY-MM-DD", "input_tokens": int,
            "output_tokens": int, "images": int}, ...],
            "total_tokens": int, "total_images": int}``.
            Days with no usage are omitted; ``by_day`` is ascending by date.
        """
        today = datetime.utcnow().date()
        cutoff = today - timedelta(days=days - 1)
        day = func.date(UsageLog.created_at)
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    day.label("d"),
                    func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input"),
                    func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output"),
                    func.coalesce(func.sum(UsageLog.images_generated), 0).label("images"),
                )
                .where(and_(UsageLog.user_id == user_id, day >= cutoff))
                .group_by(day)
                .order_by(day))
            rows = result.all()

        by_day = [{
            "date": r.d.isoformat(),
            "input_tokens": int(r.input),
            "output_tokens": int(r.output),
            "images": int(r.images),
        } for r in rows]
        return {
            "by_day": by_day,
            "total_tokens": sum(d["input_tokens"] + d["output_tokens"] for d in by_day),
            "total_images": sum(d["images"] for d in by_day),
        }

    async def get_daily_images(self, user_id: str) -> int:
        """Sum of images_generated for user today (UTC).

        Parameters
        ----------
        user_id : str
            User UUID as string.

        Returns
        -------
        int
            Total images generated today.
        """
        today = datetime.utcnow().date()
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(UsageLog.images_generated), 0))
                .where(and_(
                    UsageLog.user_id == user_id,
                    func.date(UsageLog.created_at) == today,
                ))
            )
            return result.scalar_one()
