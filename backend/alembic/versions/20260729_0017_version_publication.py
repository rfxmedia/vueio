"""add tracker version publication state

Revision ID: 20260729_0017
Revises: 20260728_0016
Create Date: 2026-07-29 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260729_0017'
down_revision = '20260728_0016'
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns('horizons_shot_versions')}


def upgrade() -> None:
    columns = _columns()
    added_share_state = 'share_state' not in columns
    if 'share_state' not in columns:
        op.add_column(
            'horizons_shot_versions',
            sa.Column('share_state', sa.String(), nullable=False, server_default='published'),
        )
    if 'published_at' not in columns:
        op.add_column('horizons_shot_versions', sa.Column('published_at', sa.Float(), nullable=True))
    if added_share_state:
        op.execute(
            "UPDATE horizons_shot_versions "
            "SET share_state = 'published', published_at = COALESCE(published_at, created_at)"
        )
    else:
        op.execute(
            "UPDATE horizons_shot_versions "
            "SET published_at = COALESCE(published_at, created_at) "
            "WHERE share_state = 'published'"
        )


def downgrade() -> None:
    columns = _columns()
    if 'published_at' in columns:
        op.drop_column('horizons_shot_versions', 'published_at')
    if 'share_state' in columns:
        op.drop_column('horizons_shot_versions', 'share_state')
