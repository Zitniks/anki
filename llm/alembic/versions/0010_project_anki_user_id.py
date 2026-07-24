"""Add projects.anki_user_id (per-Anki-user project isolation, Epic 2)

Every Anki Lite user currently shares one repetitor service account, so
without a way to tell them apart, all Anki users' chat history, BKT mastery,
and learning events were being collapsed into a single shared project. This
column lets `resolve_session` look up (or create) a distinct project per
Anki user id instead.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("anki_user_id", sa.BigInteger(), nullable=True))
    op.create_index(
        "ix_projects_anki_user_id",
        "projects",
        ["anki_user_id"],
        unique=True,
        postgresql_where=sa.text("anki_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_projects_anki_user_id", table_name="projects")
    op.drop_column("projects", "anki_user_id")
