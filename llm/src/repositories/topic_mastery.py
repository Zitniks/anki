"""Repository for TopicMastery (Student Model)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from database import TopicMastery
from repositories.base import BaseRepository
from analytics.als import calculate_als
from analytics import bkt as bkt_algo
from analytics import forgetting
from analytics.calibration import update_calibration


class TopicMasteryRepository(BaseRepository[TopicMastery]):
    """CRUD + upsert logic for TopicMastery records."""

    model = TopicMastery

    async def get_by_project(self, project_id: str) -> list[dict]:
        """Return all topic mastery records for a project, sorted by topic name.

        Parameters
        ----------
        project_id : str
            Project UUID string.

        Returns
        -------
        list[dict]
            Full Student Model as a list of topic mastery dicts.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TopicMastery)
                .where(TopicMastery.project_id == project_id)
                .order_by(TopicMastery.topic)
            )
            records = [e.to_dict() for e in result.scalars().all()]
            return forgetting.apply(records)

    async def get_by_topic(self, project_id: str, topic: str) -> dict | None:
        """Return mastery record for a single topic.

        Parameters
        ----------
        project_id : str
            Project UUID string.
        topic : str
            Topic name.

        Returns
        -------
        dict or None
            Serialised TopicMastery dict, or None if not yet seen.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TopicMastery).where(
                    TopicMastery.project_id == project_id,
                    TopicMastery.topic == topic,
                )
            )
            entity = result.scalar_one_or_none()
            return entity.to_dict() if entity else None

    async def get_weak(self, project_id: str, limit: int = 10, min_attempts: int = 3) -> list[dict]:
        """Return the project's weakest word-topics, lowest `als_score` first.

        Scoped to Anki-originated word-topics (`topic` prefixed `"word:"`, per the
        Anki learning-events convention) — grammar topics from chat/practice aren't
        relevant to Anki's "Слабые темы" screen. `als_score` (not `mastery_score`)
        matches the ranking `adaptive/engine.py::_pick_weakest` already uses, since
        it blends accuracy/time/hints/mastery into one score.

        Parameters
        ----------
        project_id : str
            Project UUID string.
        limit : int, optional
            Maximum number of topics to return (default 10).
        min_attempts : int, optional
            Minimum `total_attempts` required to avoid surfacing noise from
            barely-seen words (default 3).

        Returns
        -------
        list[dict]
            Serialised TopicMastery dicts, weakest (`als_score` ascending) first.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TopicMastery)
                .where(
                    TopicMastery.project_id == project_id,
                    TopicMastery.total_attempts >= min_attempts,
                    TopicMastery.topic.like("word:%"),
                    TopicMastery.is_mastered.is_(False),
                )
                .order_by(TopicMastery.als_score.asc())
                .limit(limit)
            )
            return [e.to_dict() for e in result.scalars().all()]

    async def update_from_event(
        self,
        project_id: str,
        topic: str,
        correct: bool,
        time_seconds: int,
        attempts: int,
        hint_used: bool,
        confidence: int | None,
        event_at: datetime,
    ) -> dict:
        """Upsert TopicMastery using BKT + ALS after a learning event.

        Parameters
        ----------
        project_id : str
            Project UUID string.
        topic : str
            Topic name.
        correct : bool
            Whether the answer was correct.
        time_seconds : int
            Time spent on the exercise.
        attempts : int
            Number of attempts for this exercise.
        hint_used : bool
            Whether a hint was used.
        confidence : int or None
            Self-assessed confidence 1–5, or None if not provided.
        event_at : datetime
            Timestamp of the learning event.

        Returns
        -------
        dict
            Updated TopicMastery dict with BKT state and ALS.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TopicMastery).where(
                    TopicMastery.project_id == project_id,
                    TopicMastery.topic == topic,
                )
            )
            rec = result.scalar_one_or_none()

            # ── Rolling stats ──────────────────────────────────────────────
            if rec is None:
                new_total = 1
                new_correct = 1 if correct else 0
                new_avg_time = float(time_seconds)
                new_hint_rate = 1.0 if hint_used else 0.0
                # BKT: start from literature defaults
                p_know = bkt_algo.DEFAULT_P_KNOW
                p_transit = bkt_algo.DEFAULT_P_TRANSIT
                p_guess = bkt_algo.DEFAULT_P_GUESS
                p_slip = bkt_algo.DEFAULT_P_SLIP
            else:
                new_total = rec.total_attempts + 1
                new_correct = rec.correct_attempts + (1 if correct else 0)
                prev_avg = rec.avg_time_seconds or float(time_seconds)
                new_avg_time = (prev_avg * rec.total_attempts + time_seconds) / new_total
                prev_hints = (rec.hint_usage_rate or 0.0) * rec.total_attempts
                new_hint_rate = (prev_hints + (1 if hint_used else 0)) / new_total
                p_know = rec.bkt_p_know
                p_transit = rec.bkt_p_transit
                p_guess = rec.bkt_p_guess
                p_slip = rec.bkt_p_slip

            # ── BKT update ─────────────────────────────────────────────────
            new_p_know = bkt_algo.update(p_know, correct, p_transit, p_guess, p_slip)
            p_correct_next = bkt_algo.predict_correct(new_p_know, p_guess, p_slip)
            mastered = bkt_algo.is_mastered(new_p_know)

            # mastery_score mirrors BKT P(know) for use by Adaptive Engine
            new_mastery = new_p_know

            # ── Confidence Calibration ─────────────────────────────────────
            accuracy = new_correct / new_total
            confidence_norm = ((confidence - 1) / 4.0) if confidence is not None else 0.5
            prev_avg_conf = rec.avg_confidence if rec is not None else None
            avg_conf, conf_bias, calib_error = update_calibration(
                prev_avg_confidence=prev_avg_conf,
                new_confidence=confidence_norm,
                total_attempts=new_total,
                accuracy=accuracy,
            )

            # ── ALS ────────────────────────────────────────────────────────
            als = calculate_als(
                accuracy=accuracy,
                time_seconds=float(time_seconds),
                avg_attempts=float(attempts),
                hint_rate=new_hint_rate,
                confidence=confidence_norm,
                mastery=new_mastery,
            )

            # ── Persist ────────────────────────────────────────────────────
            if rec is None:
                rec = TopicMastery(
                    project_id=project_id,
                    topic=topic,
                    mastery_score=new_mastery,
                    als_score=als,
                    total_attempts=new_total,
                    correct_attempts=new_correct,
                    avg_time_seconds=new_avg_time,
                    hint_usage_rate=new_hint_rate,
                    last_event_at=event_at,
                    bkt_p_know=new_p_know,
                    bkt_p_transit=p_transit,
                    bkt_p_guess=p_guess,
                    bkt_p_slip=p_slip,
                    bkt_p_correct_next=p_correct_next,
                    is_mastered=mastered,
                    avg_confidence=avg_conf,
                    confidence_bias=conf_bias,
                    calibration_error=calib_error,
                )
                session.add(rec)
            else:
                rec.mastery_score = new_mastery
                rec.als_score = als
                rec.total_attempts = new_total
                rec.correct_attempts = new_correct
                rec.avg_time_seconds = new_avg_time
                rec.hint_usage_rate = new_hint_rate
                rec.last_event_at = event_at
                rec.bkt_p_know = new_p_know
                rec.bkt_p_transit = p_transit
                rec.bkt_p_guess = p_guess
                rec.bkt_p_slip = p_slip
                rec.bkt_p_correct_next = p_correct_next
                rec.is_mastered = mastered
                rec.avg_confidence = avg_conf
                rec.confidence_bias = conf_bias
                rec.calibration_error = calib_error

            await session.commit()
            await session.refresh(rec)
            return rec.to_dict()
