"""move tool settings from projects to trackers

Revision ID: 20260719_0013
Revises: 20260713_0012
Create Date: 2026-07-19 23:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260719_0013'
down_revision = '20260713_0012'
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if 'settings_json' not in _columns('horizons_trackers'):
        op.add_column('horizons_trackers', sa.Column('settings_json', sa.Text(), nullable=True))
    if 'project_tools_json' in _columns('horizons_projects'):
        op.drop_column('horizons_projects', 'project_tools_json')


def downgrade() -> None:
    if 'project_tools_json' not in _columns('horizons_projects'):
        op.add_column('horizons_projects', sa.Column('project_tools_json', sa.Text(), nullable=True))
    if 'settings_json' in _columns('horizons_trackers'):
        op.drop_column('horizons_trackers', 'settings_json')
