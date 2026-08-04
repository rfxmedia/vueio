"""make agent mutation receipts idempotency keys unique

Revision ID: 20260713_0008
Revises: 20260713_0007
Create Date: 2026-07-13 16:00:00

Integration note: this ops revision is chained after the media branch's
20260713_0007 file-operation journal migration.
"""

from alembic import op
import sqlalchemy as sa

revision = '20260713_0008'
down_revision = '20260713_0007'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if not _has_table('agent_mutation_receipts'):
        op.create_table(
            'agent_mutation_receipts',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('agent_key_id', sa.String(), nullable=False),
            sa.Column('operation', sa.String(), nullable=False),
            sa.Column('idempotency_key', sa.String(), nullable=False),
            sa.Column('response_json', sa.Text(), nullable=False),
            sa.Column('created_at', sa.Float(), nullable=True),
        )
    op.execute('CREATE INDEX IF NOT EXISTS idx_agent_mutation_receipts_key ON agent_mutation_receipts (agent_key_id)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_agent_mutation_receipts_op ON agent_mutation_receipts (operation)')
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_mutation_receipts_key_operation_idempotency '
        'ON agent_mutation_receipts (agent_key_id, operation, idempotency_key)'
    )


def downgrade() -> None:
    if not _has_table('agent_mutation_receipts'):
        return
    op.execute(
        'ALTER TABLE agent_mutation_receipts '
        'DROP CONSTRAINT IF EXISTS uq_agent_mutation_receipts_key_operation_idempotency'
    )
    op.execute('DROP INDEX IF EXISTS uq_agent_mutation_receipts_key_operation_idempotency')
    op.execute('DROP INDEX IF EXISTS idx_agent_mutation_receipts_op')
    op.execute('DROP INDEX IF EXISTS idx_agent_mutation_receipts_key')
