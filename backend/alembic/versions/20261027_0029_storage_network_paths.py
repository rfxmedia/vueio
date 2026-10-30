"""store the network path of each storage location

Revision ID: 20261027_0029
Revises: 20261024_0028
Create Date: 2026-10-27 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20261027_0029'
down_revision = '20261024_0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if 'storage_network_paths' not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            'storage_network_paths',
            sa.Column('root_id', sa.String(), primary_key=True),
            sa.Column('network_path', sa.String(), nullable=False),
            sa.Column('updated_by', sa.String(), nullable=True),
            sa.Column('updated_at', sa.Float(), nullable=True),
        )


def downgrade() -> None:
    if 'storage_network_paths' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('storage_network_paths')
