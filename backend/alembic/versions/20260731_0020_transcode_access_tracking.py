"""track derived transcode access for bounded cache eviction

Revision ID: 20260731_0020
Revises: 20260731_0019
Create Date: 2026-07-31 14:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260731_0020'
down_revision = '20260731_0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('transcodes')}
    if 'last_accessed' not in columns:
        op.add_column('transcodes', sa.Column('last_accessed', sa.Float(), nullable=True))
    op.execute('UPDATE transcodes SET last_accessed = created_at WHERE last_accessed IS NULL')
    indexes = {index['name'] for index in sa.inspect(op.get_bind()).get_indexes('transcodes')}
    if 'ix_transcodes_last_accessed' not in indexes:
        op.create_index('ix_transcodes_last_accessed', 'transcodes', ['last_accessed'], unique=False)


def downgrade() -> None:
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('transcodes')}
    if 'last_accessed' not in columns:
        return
    indexes = {index['name'] for index in sa.inspect(op.get_bind()).get_indexes('transcodes')}
    if 'ix_transcodes_last_accessed' in indexes:
        op.drop_index('ix_transcodes_last_accessed', table_name='transcodes')
    op.drop_column('transcodes', 'last_accessed')
