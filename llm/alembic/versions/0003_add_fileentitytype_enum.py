"""create fileentitytype enum and fix files.entity_type column

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the PostgreSQL ENUM type that SQLAlchemy's SAEnum expects
    fileentitytype = sa.Enum("message", "material", "repeat_item", name="fileentitytype")
    fileentitytype.create(op.get_bind(), checkfirst=True)

    # Alter the column from VARCHAR to the enum type
    op.execute("ALTER TABLE files ALTER COLUMN entity_type TYPE fileentitytype USING entity_type::fileentitytype")


def downgrade() -> None:
    op.execute("ALTER TABLE files ALTER COLUMN entity_type TYPE VARCHAR(50) USING entity_type::VARCHAR")
    op.execute("DROP TYPE IF EXISTS fileentitytype")
