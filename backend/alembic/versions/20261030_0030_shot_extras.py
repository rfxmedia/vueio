"""store the extras of shots and the file of each extra for each version

Revision ID: 20261030_0030
Revises: 20261027_0029
Create Date: 2026-10-30 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20261030_0030'
down_revision = '20261027_0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'horizons_shot_extras' not in tables:
        op.create_table(
            'horizons_shot_extras',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('tracker_id', sa.String(), nullable=False),
            sa.Column('shot_id', sa.String(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('note', sa.String(), nullable=True),
            sa.Column('client_visible', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_by', sa.String(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=True),
            sa.Column('updated_at', sa.Float(), nullable=True),
        )
        for column in ('project_id', 'tracker_id', 'shot_id'):
            op.create_index(f'ix_horizons_shot_extras_{column}', 'horizons_shot_extras', [column])
        op.create_index('ix_horizons_shot_extras_shot_order', 'horizons_shot_extras', ['shot_id', 'sort_order'])
    if 'horizons_shot_extra_files' not in tables:
        op.create_table(
            'horizons_shot_extra_files',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('tracker_id', sa.String(), nullable=False),
            sa.Column('shot_id', sa.String(), nullable=False),
            sa.Column('extra_id', sa.String(), nullable=False),
            sa.Column('version_id', sa.String(), nullable=False),
            sa.Column('media_asset_id', sa.String(), nullable=False),
            sa.Column('created_by', sa.String(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=True),
            sa.Column('updated_at', sa.Float(), nullable=True),
            sa.UniqueConstraint('extra_id', 'version_id', name='uq_horizons_shot_extra_files_extra_version'),
        )
        for column in ('project_id', 'tracker_id', 'shot_id', 'extra_id', 'version_id', 'media_asset_id'):
            op.create_index(f'ix_horizons_shot_extra_files_{column}', 'horizons_shot_extra_files', [column])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ('horizons_shot_extra_files', 'horizons_shot_extras'):
        if table in tables:
            op.drop_table(table)
