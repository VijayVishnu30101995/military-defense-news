"""Add role to users

Revision ID: a3f9c2d1e7b4
Revises: 4630948df0b2
Create Date: 2026-10-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c2d1e7b4'
down_revision: Union[str, Sequence[str], None] = '4630948df0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing users had full access before roles existed, so keep them as admins.
    op.add_column(
        'users',
        sa.Column('role', sa.String(length=20), server_default='admin', nullable=False),
    )
    # New users default to read-only access.
    op.alter_column('users', 'role', server_default='viewer')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'role')
