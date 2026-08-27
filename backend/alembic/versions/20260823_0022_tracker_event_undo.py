"""record conflict-safe tracker event undo links

Revision ID: 20260823_0022
Revises: 20260810_0021
Create Date: 2026-08-23 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20260823_0022'
down_revision = '20260810_0021'
branch_labels = None
depends_on = None


INDEX_NAME = 'uq_tracker_events_undo_of_event_id'


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('tracker_events')}
    if 'undo_of_event_id' not in columns:
        op.add_column('tracker_events', sa.Column('undo_of_event_id', sa.Integer(), nullable=True))

    inspector = sa.inspect(op.get_bind())
    indexes = {index['name'] for index in inspector.get_indexes('tracker_events')}
    indexes.update(
        constraint['name']
        for constraint in inspector.get_unique_constraints('tracker_events')
        if constraint.get('name')
    )
    if INDEX_NAME not in indexes:
        op.create_index(INDEX_NAME, 'tracker_events', ['undo_of_event_id'], unique=True)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index['name'] for index in inspector.get_indexes('tracker_events')}
    indexes.update(
        constraint['name']
        for constraint in inspector.get_unique_constraints('tracker_events')
        if constraint.get('name')
    )
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name='tracker_events')

    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('tracker_events')}
    if 'undo_of_event_id' in columns:
        op.drop_column('tracker_events', 'undo_of_event_id')
