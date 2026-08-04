"""bind authenticated upload sessions to their initiating account

Revision ID: 20260731_0018
Revises: 20260729_0017
Create Date: 2026-07-31 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260731_0018'
down_revision = '20260729_0017'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('upload_sessions')}


def upgrade() -> None:
    if 'owner_user_id' not in _columns():
        op.add_column('upload_sessions', sa.Column('owner_user_id', sa.String(), nullable=True))
    indexes = {
        index['name']
        for index in sa.inspect(op.get_bind()).get_indexes('upload_sessions')
    }
    if 'ix_upload_sessions_owner_user_id' not in indexes:
        op.create_index(
            'ix_upload_sessions_owner_user_id',
            'upload_sessions',
            ['owner_user_id'],
            unique=False,
        )


def downgrade() -> None:
    if 'owner_user_id' in _columns():
        indexes = {
            index['name']
            for index in sa.inspect(op.get_bind()).get_indexes('upload_sessions')
        }
        if 'ix_upload_sessions_owner_user_id' in indexes:
            op.drop_index('ix_upload_sessions_owner_user_id', table_name='upload_sessions')
        op.drop_column('upload_sessions', 'owner_user_id')
