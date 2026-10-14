"""Add text_lookup_at and text_credit to articles

text_lookup_at records when a story stored without body text had its page (or another
outlet's copy) read for the opening paragraphs, so each story is tried once rather than on
every collection run. text_credit names the outlet whose copy supplied the text.

Revision ID: d9f3b7c2e5a8
Revises: c8a4f2e9d1b3
Create Date: 2026-10-14 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9f3b7c2e5a8'
down_revision: Union[str, Sequence[str], None] = 'c8a4f2e9d1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('text_lookup_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('articles', sa.Column('text_credit', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('articles', 'text_credit')
    op.drop_column('articles', 'text_lookup_at')
