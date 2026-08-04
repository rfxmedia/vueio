"""add comment annotation targets

Revision ID: 20260623_0002
Revises: 20260329_0001
Create Date: 2026-06-23 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260623_0002'
down_revision = '20260329_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column['name'] for column in sa.inspect(bind).get_columns('comments')}
    if 'annotation_target' not in columns:
        op.add_column('comments', sa.Column('annotation_target', sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column['name'] for column in sa.inspect(bind).get_columns('comments')}
    if 'annotation_target' in columns:
        op.drop_column('comments', 'annotation_target')
