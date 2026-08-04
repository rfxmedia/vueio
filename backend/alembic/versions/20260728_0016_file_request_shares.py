"""add explicit file request shares

Revision ID: 20260728_0016
Revises: 20260722_0015
Create Date: 2026-07-28 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260728_0016'
down_revision = '20260722_0015'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('shares')}


def upgrade() -> None:
    if 'request_files' not in _columns():
        op.add_column('shares', sa.Column('request_files', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    if 'request_files' in _columns():
        op.drop_column('shares', 'request_files')
