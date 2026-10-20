"""add a short tracker description

Revision ID: 20261019_0025
Revises: 20260906_0024
Create Date: 2026-10-19 10:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20261019_0025'
down_revision = '20260906_0024'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('horizons_trackers')}


def upgrade() -> None:
    if 'description' not in _columns():
        op.add_column('horizons_trackers', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    if 'description' in _columns():
        op.drop_column('horizons_trackers', 'description')
