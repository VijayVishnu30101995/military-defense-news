"""Add position to article_categories

Revision ID: c2a5f8b3e6d1
Revises: b7e4c1a9d2f3
Create Date: 2026-10-08 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2a5f8b3e6d1'
down_revision: Union[str, Sequence[str], None] = 'b7e4c1a9d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Null for rows written before the category ranking was kept; those keep sorting
    # by name until their article is collected again.
    op.add_column('article_categories', sa.Column('position', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('article_categories', 'position')
