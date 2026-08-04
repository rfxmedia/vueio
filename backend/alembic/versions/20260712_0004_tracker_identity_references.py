"""add immutable tracker identity references

Revision ID: 20260712_0004
Revises: 20260705_0003
Create Date: 2026-07-12 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260712_0004'
down_revision = '20260705_0003'
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def _backfill(table_name: str, *, tracker_shares_only: bool = False) -> None:
    share_filter = "AND share_type = 'tracker'" if tracker_shares_only else ''
    op.execute(f"""
        UPDATE {table_name}
        SET tracker_id = (
            SELECT tracker.id
            FROM horizons_trackers AS tracker
            WHERE tracker.project_id = {table_name}.project_id
              AND (
                tracker.id = {table_name}.tracker_name
                OR tracker.slug = {table_name}.tracker_name
                OR tracker.name = {table_name}.tracker_name
              )
            LIMIT 1
        )
        WHERE tracker_id IS NULL
          AND project_id IS NOT NULL
          AND tracker_name IS NOT NULL
          AND TRIM(tracker_name) != ''
          {share_filter}
          AND 1 = (
            SELECT COUNT(*)
            FROM horizons_trackers AS tracker
            WHERE tracker.project_id = {table_name}.project_id
              AND (
                tracker.id = {table_name}.tracker_name
                OR tracker.slug = {table_name}.tracker_name
                OR tracker.name = {table_name}.tracker_name
              )
          )
    """)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in ('shares', 'version_registry', 'shot_registry'):
        if table_name in tables and 'tracker_id' not in _columns(table_name):
            op.add_column(table_name, sa.Column('tracker_id', sa.String(), nullable=True))

    can_backfill = 'horizons_trackers' in tables
    if 'shares' in tables:
        if can_backfill:
            _backfill('shares', tracker_shares_only=True)
        op.execute('CREATE INDEX IF NOT EXISTS idx_shares_project_tracker ON shares (project_id, tracker_id)')
    if 'version_registry' in tables:
        if can_backfill:
            _backfill('version_registry')
        op.execute('CREATE INDEX IF NOT EXISTS idx_version_registry_project_tracker_id ON version_registry (project_id, tracker_id)')
    if 'shot_registry' in tables:
        if can_backfill:
            _backfill('shot_registry')
        op.execute('CREATE INDEX IF NOT EXISTS idx_shot_registry_project_tracker_id ON shot_registry (project_id, tracker_id)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_shot_registry_project_tracker_id')
    op.execute('DROP INDEX IF EXISTS idx_version_registry_project_tracker_id')
    op.execute('DROP INDEX IF EXISTS idx_shares_project_tracker')

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in ('shot_registry', 'version_registry', 'shares'):
        if table_name in tables and 'tracker_id' in _columns(table_name):
            op.drop_column(table_name, 'tracker_id')
