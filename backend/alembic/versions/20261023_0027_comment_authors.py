"""record who wrote a comment and when it was last edited

Revision ID: 20261023_0027
Revises: 20261023_0026
Create Date: 2026-10-23 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20261023_0027'
down_revision = '20261023_0026'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('comments')}


def _indexes() -> set[str]:
    return {index['name'] for index in sa.inspect(op.get_bind()).get_indexes('comments')}


def upgrade() -> None:
    columns = _columns()
    if 'author_user_id' not in columns:
        op.add_column('comments', sa.Column('author_user_id', sa.String(), nullable=True))
    if 'edited_at' not in columns:
        op.add_column('comments', sa.Column('edited_at', sa.Float(), nullable=True))
    if 'ix_comments_author_user_id' not in _indexes():
        op.create_index('ix_comments_author_user_id', 'comments', ['author_user_id'], unique=False)
    # Tracker history recorded the signed-in author of most existing comments.
    op.execute(sa.text("""
        UPDATE comments SET author_user_id = (
            SELECT tracker_events.actor_id FROM tracker_events
            WHERE tracker_events.event_type = 'comment_added'
              AND tracker_events.comment_id = CAST(comments.id AS VARCHAR)
              AND tracker_events.actor_id IS NOT NULL
            ORDER BY tracker_events.id ASC
            LIMIT 1
        )
        WHERE author_user_id IS NULL
    """))


def downgrade() -> None:
    if 'ix_comments_author_user_id' in _indexes():
        op.drop_index('ix_comments_author_user_id', table_name='comments')
    columns = _columns()
    if 'edited_at' in columns:
        op.drop_column('comments', 'edited_at')
    if 'author_user_id' in columns:
        op.drop_column('comments', 'author_user_id')
