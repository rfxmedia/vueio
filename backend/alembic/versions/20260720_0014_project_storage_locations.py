"""add project storage locations

Revision ID: 20260720_0014
Revises: 20260719_0013
Create Date: 2026-07-20 19:15:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260720_0014'
down_revision = '20260719_0013'
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    columns = _columns('horizons_projects')
    if 'storage_root' not in columns:
        op.add_column(
            'horizons_projects',
            sa.Column('storage_root', sa.String(), nullable=False, server_default='data'),
        )
    if 'storage_path' not in columns:
        op.add_column('horizons_projects', sa.Column('storage_path', sa.String(), nullable=True))
    op.execute(sa.text("UPDATE horizons_projects SET storage_path = id WHERE storage_path IS NULL OR storage_path = ''"))
    indexes = {index['name'] for index in sa.inspect(op.get_bind()).get_indexes('horizons_projects')}
    if 'ix_horizons_projects_storage_root' not in indexes:
        op.create_index('ix_horizons_projects_storage_root', 'horizons_projects', ['storage_root'], unique=False)


def downgrade() -> None:
    indexes = {index['name'] for index in sa.inspect(op.get_bind()).get_indexes('horizons_projects')}
    if 'ix_horizons_projects_storage_root' in indexes:
        op.drop_index('ix_horizons_projects_storage_root', table_name='horizons_projects')
    columns = _columns('horizons_projects')
    if 'storage_path' in columns:
        op.drop_column('horizons_projects', 'storage_path')
    if 'storage_root' in columns:
        op.drop_column('horizons_projects', 'storage_root')
