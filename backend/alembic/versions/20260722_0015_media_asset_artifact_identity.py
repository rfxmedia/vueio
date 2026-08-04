"""add stable media artifact identity

Revision ID: 20260722_0015
Revises: 20260720_0014
Create Date: 2026-07-22 12:15:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260722_0015'
down_revision = '20260720_0014'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('media_assets')}


def upgrade() -> None:
    if 'artifact_identity' not in _columns():
        op.add_column('media_assets', sa.Column('artifact_identity', sa.String(), nullable=True))


def downgrade() -> None:
    if 'artifact_identity' in _columns():
        op.drop_column('media_assets', 'artifact_identity')
