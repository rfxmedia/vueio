"""store compact tracker history snapshots

Revision ID: 20260824_0023
Revises: 20260823_0022
Create Date: 2026-08-24 10:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20260824_0023'
down_revision = '20260823_0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('tracker_events')}
    if 'state_snapshot' not in columns:
        op.add_column('tracker_events', sa.Column('state_snapshot', sa.LargeBinary(), nullable=True))
    if 'state_hash' not in columns:
        op.add_column('tracker_events', sa.Column('state_hash', sa.String(), nullable=True))


def downgrade() -> None:
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('tracker_events')}
    if 'state_hash' in columns:
        op.drop_column('tracker_events', 'state_hash')
    if 'state_snapshot' in columns:
        op.drop_column('tracker_events', 'state_snapshot')
