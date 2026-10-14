"""Add why_it_matters to articles

Written by the AI key points pass together with key_points: one or two sentences on why
the story matters.

Revision ID: a3b9d5f1c7e2
Revises: d9f3b7c2e5a8
Create Date: 2026-10-14 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b9d5f1c7e2'
down_revision: Union[str, Sequence[str], None] = 'd9f3b7c2e5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('why_it_matters', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('articles', 'why_it_matters')
