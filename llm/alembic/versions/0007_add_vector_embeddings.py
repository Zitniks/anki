"""Add pgvector embedding column to materials

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE materials ADD COLUMN embedding vector(384)")
    # hnsw works on empty tables; ivfflat requires rows >= lists
    op.execute("""
        CREATE INDEX ix_materials_embedding
        ON materials
        USING hnsw(embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_materials_embedding")
    op.execute("ALTER TABLE materials DROP COLUMN IF EXISTS embedding")
