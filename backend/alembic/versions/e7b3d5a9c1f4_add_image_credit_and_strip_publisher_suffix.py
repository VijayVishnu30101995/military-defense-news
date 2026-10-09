"""Add image_credit to articles and strip " - Reuters" from stored Google News titles

Revision ID: e7b3d5a9c1f4
Revises: d4e8a1c7f2b9
Create Date: 2026-10-09 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b3d5a9c1f4'
down_revision: Union[str, Sequence[str], None] = 'd4e8a1c7f2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('image_credit', sa.String(length=255), nullable=True))

    # The collector now drops the publisher suffix Google News appends to headlines; bring
    # stored rows in line so they match the same wire story republished by other outlets.
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(
        r"""
        UPDATE articles
        SET title = left(title, length(title) - length(' - Reuters')),
            normalized_title = regexp_replace(normalized_title, '\s+reuters$', ''),
            content_hash = encode(
                sha256(convert_to(regexp_replace(normalized_title, '\s+reuters$', ''), 'UTF8')),
                'hex'
            )
        WHERE original_url LIKE 'https://news.google.com/%'
          AND title LIKE '% - Reuters'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Stripped title suffixes are not restored; they were redundant with the source name.
    op.drop_column('articles', 'image_credit')
