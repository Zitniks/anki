"""Vocabulary repository"""

from datetime import datetime
from sqlalchemy import select, and_

from database import Vocabulary
from repositories.base import BaseRepository
from logger import db_logger


class VocabularyRepository(BaseRepository[Vocabulary]):
    model = Vocabulary

    async def get_active_by_project(self, project_id: str) -> list[dict]:
        """Non-deleted vocabulary for a project, ordered by extracted_at asc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Vocabulary)
                .where(and_(
                    Vocabulary.project_id == project_id,
                    Vocabulary.is_deleted == False,  # noqa: E712
                ))
                .order_by(Vocabulary.extracted_at.asc())
            )
            items = result.scalars().all()
            return [item.to_dict() for item in items]

    async def add_words(self, project_id: str, words: list[str]) -> dict[str, list[str]]:
        """Sanitize, deduplicate, and persist vocabulary words.

        Parameters
        ----------
        project_id : str
            Project to add words to.
        words : list[str]
            Raw words from caller (may contain duplicates, mixed case, whitespace).

        Returns
        -------
        dict[str, list[str]]
            Keys: ``added``, ``skipped_existing``, ``skipped_deleted``, ``rejected``.
        """
        seen: set[str] = set()
        clean: list[str] = []
        rejected: list[str] = []
        for w in words:
            w = w.strip().lower()
            if not w or len(w) > 500:
                rejected.append(w or "<empty>")
                continue
            if w in seen:
                continue
            seen.add(w)
            clean.append(w)

        async with self._session_factory() as session:
            result = await session.execute(
                select(Vocabulary.word, Vocabulary.is_deleted).where(Vocabulary.project_id == project_id))
            existing_data = {row[0]: row[1] for row in result.all()}

            added: list[str] = []
            skipped_existing: list[str] = []
            skipped_deleted: list[str] = []
            new_items = []
            for word in clean:
                if word not in existing_data:
                    new_items.append(Vocabulary(project_id=project_id, word=word))
                    added.append(word)
                elif existing_data[word]:
                    skipped_deleted.append(word)
                    db_logger.debug(f"db.vocab_skip_deleted project_id={project_id} word={word}")
                else:
                    skipped_existing.append(word)

            if new_items:
                session.add_all(new_items)
                await session.commit()
                db_logger.info(f"db.vocab_create project_id={project_id} count={len(new_items)}")

        return {
            "added": added,
            "skipped_existing": skipped_existing,
            "skipped_deleted": skipped_deleted,
            "rejected": rejected,
        }

    async def update_words(self, project_id: str, words: list[str]) -> None:
        """Replace active vocabulary: soft-delete removed, add new."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Vocabulary)
                .where(and_(
                    Vocabulary.project_id == project_id,
                    Vocabulary.is_deleted == False,  # noqa: E712
                )))
            existing_items = result.scalars().all()
            existing_words = {item.word for item in existing_items}

            words_to_keep = set(words)
            for item in existing_items:
                if item.word not in words_to_keep:
                    item.is_deleted = True
                    item.deleted_at = datetime.utcnow()

            for word in words:
                if word not in existing_words:
                    session.add(Vocabulary(project_id=project_id, word=word))

            await session.commit()

    async def soft_delete_by_id(self, project_id: str, word_id: int) -> bool:
        """Soft-delete a vocabulary item by its integer ID. Returns False if not found."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Vocabulary)
                .where(and_(
                    Vocabulary.id == word_id,
                    Vocabulary.project_id == project_id,
                    Vocabulary.is_deleted == False,  # noqa: E712
                )))
            vocab_item = result.scalar_one_or_none()
            if not vocab_item:
                return False

            vocab_item.is_deleted = True
            vocab_item.deleted_at = datetime.utcnow()
            await session.commit()
            db_logger.info(f"db.vocab_delete project_id={project_id} word_id={word_id}")
            return True

    async def cleanup_deleted(self) -> int:
        """Permanently remove ALL soft-deleted items."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Vocabulary)
                .where(Vocabulary.is_deleted == True)   # noqa: E712
            )
            all_deleted = result.scalars().all()

            for item in all_deleted:
                await session.delete(item)

            await session.commit()
            db_logger.info(f"db.vocab_cleanup count={len(all_deleted)}")
            return len(all_deleted)
