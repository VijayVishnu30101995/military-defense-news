"""Create watchlists and watchlist_matches

Readers save topics (watchlists); stories that mention them are recorded as matches, which
drive the in-app unread counts and the email alerts.

Revision ID: f1c7a3e9b5d2
Revises: d9f3b7c2e5a8
Create Date: 2026-10-14 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c7a3e9b5d2'
down_revision: Union[str, Sequence[str], None] = 'd9f3b7c2e5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'watchlists',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('terms', sa.JSON(), nullable=False),
        sa.Column('exclude_terms', sa.JSON(), nullable=False),
        sa.Column('email_frequency', sa.String(length=20), nullable=False, server_default='off'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_article_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_watchlists_user_id', 'watchlists', ['user_id'])
    op.create_table(
        'watchlist_matches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('watchlist_id', sa.Integer(), sa.ForeignKey('watchlists.id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_id', sa.Integer(), sa.ForeignKey('articles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('matched_terms', sa.JSON(), nullable=False),
        sa.Column('matched_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('emailed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('watchlist_id', 'article_id', name='uq_watchlist_match'),
    )
    op.create_index('ix_watchlist_matches_watchlist_id', 'watchlist_matches', ['watchlist_id'])
    op.create_index('ix_watchlist_matches_article_id', 'watchlist_matches', ['article_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_watchlist_matches_article_id', table_name='watchlist_matches')
    op.drop_index('ix_watchlist_matches_watchlist_id', table_name='watchlist_matches')
    op.drop_table('watchlist_matches')
    op.drop_index('ix_watchlists_user_id', table_name='watchlists')
    op.drop_table('watchlists')
