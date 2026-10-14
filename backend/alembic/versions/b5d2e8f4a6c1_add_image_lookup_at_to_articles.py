"""Add image_lookup_at to articles

Records when a photo-less story was searched for in other outlets' copies, so each story is
searched once rather than on every collection run.

Revision ID: b5d2e8f4a6c1
Revises: e7b3d5a9c1f4
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d2e8f4a6c1'
down_revision: Union[str, Sequence[str], None] = 'e7b3d5a9c1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('image_lookup_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('articles', 'image_lookup_at')
