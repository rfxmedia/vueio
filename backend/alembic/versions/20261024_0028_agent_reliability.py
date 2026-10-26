"""Retain version upload results and index expiring agent receipts.

Revision ID: 20261024_0028
Revises: 20261023_0027
"""
from alembic import op
import sqlalchemy as sa

revision = '20261024_0028'
down_revision = '20261023_0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'version_upload_json' not in {c['name'] for c in inspector.get_columns('upload_items')}:
        op.add_column('upload_items', sa.Column('version_upload_json', sa.Text(), nullable=True))
    if 'ix_agent_mutation_receipts_created_at' not in {i['name'] for i in inspector.get_indexes('agent_mutation_receipts')}:
        op.create_index('ix_agent_mutation_receipts_created_at', 'agent_mutation_receipts', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_agent_mutation_receipts_created_at', table_name='agent_mutation_receipts')
    op.drop_column('upload_items', 'version_upload_json')
