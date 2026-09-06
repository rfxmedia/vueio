"""Store the workspace's shared 3D LUT library in the database."""

from alembic import op
import sqlalchemy as sa


revision = '20260906_0024'
down_revision = '20260824_0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table('workspace_luts'):
        op.create_table(
            'workspace_luts',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('size', sa.Integer(), nullable=False),
            sa.Column('byte_size', sa.Integer(), nullable=False),
            sa.Column('cube_text', sa.Text(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table('workspace_luts')
