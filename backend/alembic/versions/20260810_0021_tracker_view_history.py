"""record privacy-safe tracker viewer history

Revision ID: 20260810_0021
Revises: 20260731_0020
Create Date: 2026-08-10 10:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260810_0021'
down_revision = '20260731_0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'tracker_view_events' not in inspector.get_table_names():
        op.create_table(
            'tracker_view_events',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=False),
            sa.Column('tracker_id', sa.String(), nullable=False),
            sa.Column('shot_id', sa.String(), nullable=True),
            sa.Column('shot_version_id', sa.String(), nullable=True),
            sa.Column('visit_id', sa.String(), nullable=False),
            sa.Column('viewer_user_id', sa.String(), nullable=True),
            sa.Column('viewer_name', sa.String(), nullable=False),
            sa.Column('source', sa.String(), nullable=False),
            sa.Column('share_id', sa.String(), nullable=True),
            sa.Column('event_type', sa.String(), nullable=False),
            sa.Column('device_type', sa.String(), nullable=False),
            sa.Column('client_metadata_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=False),
            sa.Column('last_seen_at', sa.Float(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )

    existing_indexes = {
        index['name']
        for index in sa.inspect(op.get_bind()).get_indexes('tracker_view_events')
    }
    for name, columns in (
        ('ix_tracker_view_events_history', ['project_id', 'tracker_id', 'created_at']),
        ('ix_tracker_view_events_presence', ['project_id', 'tracker_id', 'event_type', 'last_seen_at']),
        ('ix_tracker_view_events_visit', ['project_id', 'tracker_id', 'visit_id']),
        ('ix_tracker_view_events_created_at', ['created_at']),
    ):
        if name not in existing_indexes:
            op.create_index(name, 'tracker_view_events', columns, unique=False)


def downgrade() -> None:
    if 'tracker_view_events' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('tracker_view_events')
