"""Add relevance_score to articles

Revision ID: b7e4c1a9d2f3
Revises: a3f9c2d1e7b4
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e4c1a9d2f3'
down_revision: Union[str, Sequence[str], None] = 'a3f9c2d1e7b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Left null for existing rows on purpose: they keep displaying under the keyword
    # filter and get a real score the next time their source is collected.
    op.add_column('articles', sa.Column('relevance_score', sa.Integer(), nullable=True))
    op.create_index('ix_articles_relevance_score', 'articles', ['relevance_score'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_articles_relevance_score', table_name='articles')
    op.drop_column('articles', 'relevance_score')
