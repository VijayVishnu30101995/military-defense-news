"""Decode &amp; in stored image URLs

Image URLs read from page metadata were stored with their HTML entities, so a query string
like "?width=1200&amp;auth=..." reached the image server as a parameter named "amp;auth"
and was rejected (HTTP 400). The collector now decodes them; this repairs existing rows.

Revision ID: c8a4f2e9d1b3
Revises: b5d2e8f4a6c1
Create Date: 2026-10-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8a4f2e9d1b3'
down_revision: Union[str, Sequence[str], None] = 'b5d2e8f4a6c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE articles SET image_url = replace(image_url, '&amp;', '&') WHERE image_url LIKE '%&amp;%'")


def downgrade() -> None:
    """Downgrade schema."""
    # Nothing to undo: the escaped URLs never worked.
