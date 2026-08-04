"""add immutable media asset lifecycle

Revision ID: 20260713_0005
Revises: 20260712_0004
Create Date: 2026-07-13 12:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260713_0005'
down_revision = '20260712_0004'
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'media_assets' in tables:
        columns = _columns('media_assets')
        if 'source_signature' not in columns:
            op.add_column('media_assets', sa.Column('source_signature', sa.String(), nullable=True))
        if 'unavailable_at' not in columns:
            op.add_column('media_assets', sa.Column('unavailable_at', sa.Float(), nullable=True))
        if 'unavailable_reason' not in columns:
            op.add_column('media_assets', sa.Column('unavailable_reason', sa.String(), nullable=True))
        op.execute('CREATE INDEX IF NOT EXISTS idx_media_assets_source_signature ON media_assets (source_signature)')
        op.execute('CREATE INDEX IF NOT EXISTS idx_media_assets_unavailable_at ON media_assets (unavailable_at)')
        op.execute('CREATE INDEX IF NOT EXISTS idx_media_assets_project_scope_path_available ON media_assets (project_id, storage_scope, file_path, unavailable_at)')

    if 'shares' in tables:
        if 'media_asset_id' not in _columns('shares'):
            op.add_column('shares', sa.Column('media_asset_id', sa.String(), nullable=True))
        op.execute('CREATE INDEX IF NOT EXISTS idx_shares_media_asset_id ON shares (media_asset_id)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_shares_media_asset_id')
    op.execute('DROP INDEX IF EXISTS idx_media_assets_unavailable_at')
    op.execute('DROP INDEX IF EXISTS idx_media_assets_source_signature')
    op.execute('DROP INDEX IF EXISTS idx_media_assets_project_scope_path_available')
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    # Do not drop shares.media_asset_id on downgrade. Older live schemas may
    # have had this column before revision 0005 was adopted, so removing it
    # would destroy pre-existing share bindings.
    if 'media_assets' in tables:
        columns = _columns('media_assets')
        for column_name in ('unavailable_reason', 'unavailable_at', 'source_signature'):
            if column_name in columns:
                op.drop_column('media_assets', column_name)
