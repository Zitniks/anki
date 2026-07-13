"""Add full-text search to materials via tsvector + GIN index

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Generated tsvector column (computed automatically by PostgreSQL)
    op.execute("""
        ALTER TABLE materials
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(answers, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(content, '')), 'C')
        ) STORED
    """)
    # GIN index for fast full-text search
    op.execute("CREATE INDEX ix_materials_content_tsv ON materials USING GIN(content_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_materials_content_tsv")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS content_tsv")
