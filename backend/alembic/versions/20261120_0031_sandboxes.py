"""store Vue Sandboxes, their saved versions, and share links to a sandbox

Revision ID: 20261120_0031
Revises: 20261030_0030
Create Date: 2026-11-20 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20261120_0031'
down_revision = '20261030_0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if 'horizons_sandboxes' not in tables:
        op.create_table(
            'horizons_sandboxes',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('slug', sa.String(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('latest_version', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_by', sa.String(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=True),
            sa.Column('updated_at', sa.Float(), nullable=True),
            sa.UniqueConstraint('project_id', 'slug', name='uq_horizons_sandboxes_project_slug'),
        )
        op.create_index('ix_horizons_sandboxes_project_id', 'horizons_sandboxes', ['project_id'])
    if 'horizons_sandbox_versions' not in tables:
        op.create_table(
            'horizons_sandbox_versions',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('sandbox_id', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('number', sa.Integer(), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('size_bytes', sa.Integer(), nullable=False),
            sa.Column('message', sa.String(), nullable=True),
            sa.Column('restored_from', sa.Integer(), nullable=True),
            sa.Column('author_id', sa.String(), nullable=True),
            sa.Column('author_name', sa.String(), nullable=True),
            sa.Column('agent_name', sa.String(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=True),
            sa.UniqueConstraint('sandbox_id', 'number', name='uq_horizons_sandbox_versions_number'),
        )
        op.create_index('ix_horizons_sandbox_versions_sandbox_id', 'horizons_sandbox_versions', ['sandbox_id'])
        op.create_index('ix_horizons_sandbox_versions_project_id', 'horizons_sandbox_versions', ['project_id'])
    share_columns = {column['name'] for column in sa.inspect(bind).get_columns('shares')}
    if 'sandbox_id' not in share_columns:
        op.add_column('shares', sa.Column('sandbox_id', sa.String(), nullable=True))
        op.create_index('ix_shares_sandbox_id', 'shares', ['sandbox_id'])


def downgrade() -> None:
    bind = op.get_bind()
    share_columns = {column['name'] for column in sa.inspect(bind).get_columns('shares')}
    if 'sandbox_id' in share_columns:
        op.drop_index('ix_shares_sandbox_id', table_name='shares')
        op.drop_column('shares', 'sandbox_id')
    tables = set(sa.inspect(bind).get_table_names())
    for table in ('horizons_sandbox_versions', 'horizons_sandboxes'):
        if table in tables:
            op.drop_table(table)
