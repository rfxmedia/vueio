"""add durable file operation journal

Revision ID: 20260713_0007
Revises: 20260713_0006
Create Date: 2026-07-13 17:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260713_0007'
down_revision = '20260713_0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if 'file_operation_journal' not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            'file_operation_journal',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('operation_type', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('source_path', sa.String(), nullable=True),
            sa.Column('destination_path', sa.String(), nullable=True),
            sa.Column('status', sa.String(), nullable=False, server_default='pending'),
            sa.Column('payload_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('error_text', sa.Text(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=True),
            sa.Column('updated_at', sa.Float(), nullable=True),
        )
    op.create_index('idx_file_operation_journal_operation_type', 'file_operation_journal', ['operation_type'])
    op.create_index('idx_file_operation_journal_project_id', 'file_operation_journal', ['project_id'])
    op.create_index('idx_file_operation_journal_status', 'file_operation_journal', ['status'])


def downgrade() -> None:
    bind = op.get_bind()
    if 'file_operation_journal' not in set(sa.inspect(bind).get_table_names()):
        return
    op.execute('DROP INDEX IF EXISTS idx_file_operation_journal_status')
    op.execute('DROP INDEX IF EXISTS idx_file_operation_journal_project_id')
    op.execute('DROP INDEX IF EXISTS idx_file_operation_journal_operation_type')
