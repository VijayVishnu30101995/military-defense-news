"""Fix timestamp server defaults frozen at table creation

Revision ID: d4e8a1c7f2b9
Revises: c2a5f8b3e6d1
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e8a1c7f2b9'
down_revision: Union[str, Sequence[str], None] = 'c2a5f8b3e6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The original migrations passed server_default='now()' as a plain string, which renders as
# DEFAULT 'now()'. Postgres evaluates that literal once when the table is created, so every
# row got the same timestamp. sa.text('now()') makes it a function call evaluated per insert.
TIMESTAMP_COLUMNS = {
    'articles': ('collected_at', 'created_at', 'updated_at'),
    'job_runs': ('started_at', 'created_at'),
    'newsletters': ('created_at', 'updated_at'),
    'source_collection_jobs': ('created_at', 'updated_at'),
    'sources': ('created_at', 'updated_at'),
    'system_settings': ('created_at', 'updated_at'),
}


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite stores the default as an expression already and can't ALTER a column default.
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table, columns in TIMESTAMP_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, server_default=sa.text('now()'))


def downgrade() -> None:
    """Downgrade schema."""
    # Nothing to restore: the old defaults were a frozen constant, not a working value.
    pass
