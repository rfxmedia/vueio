"""add horizon tracker tags and shot archive fields

Revision ID: 20260705_0003
Revises: 20260623_0002
Create Date: 2026-07-05 21:10:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260705_0003'
down_revision = '20260623_0002'
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'horizons_trackers' in tables:
        tracker_columns = _columns('horizons_trackers')
        if 'tags_json' not in tracker_columns:
            op.add_column('horizons_trackers', sa.Column('tags_json', sa.Text(), nullable=True))

    if 'horizons_shots' in tables:
        shot_columns = _columns('horizons_shots')
        if 'archived_at' not in shot_columns:
            op.add_column('horizons_shots', sa.Column('archived_at', sa.Float(), nullable=True))
        if 'archived_by' not in shot_columns:
            op.add_column('horizons_shots', sa.Column('archived_by', sa.String(), nullable=True))
        if 'archive_reason' not in shot_columns:
            op.add_column('horizons_shots', sa.Column('archive_reason', sa.Text(), nullable=True))

        op.execute(
            'CREATE INDEX IF NOT EXISTS idx_horizons_shots_project_tracker_archived '
            'ON horizons_shots (project_id, tracker_id, archived_at)'
        )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_horizons_shots_project_tracker_archived')

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'horizons_shots' in tables:
        shot_columns = _columns('horizons_shots')
        if 'archive_reason' in shot_columns:
            op.drop_column('horizons_shots', 'archive_reason')
        if 'archived_by' in shot_columns:
            op.drop_column('horizons_shots', 'archived_by')
        if 'archived_at' in shot_columns:
            op.drop_column('horizons_shots', 'archived_at')

    if 'horizons_trackers' in tables:
        tracker_columns = _columns('horizons_trackers')
        if 'tags_json' in tracker_columns:
            op.drop_column('horizons_trackers', 'tags_json')
