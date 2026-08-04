"""baseline sqlite schema

Revision ID: 20260329_0001
Revises:
Create Date: 2026-03-29 01:10:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260329_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('project_id', sa.String(), nullable=True),
        sa.Column('horizons_media_asset_id', sa.String(), nullable=True),
        sa.Column('horizons_shot_version_id', sa.String(), nullable=True),
        sa.Column('user_name', sa.String(), nullable=True),
        sa.Column('timestamp', sa.Float(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=True),
        sa.Column('parent_comment_id', sa.Integer(), nullable=True),
        sa.Column('root_comment_id', sa.Integer(), nullable=True),
        sa.Column('annotation_data', sa.Text(), nullable=True),
        sa.Column('attachments_data', sa.Text(), nullable=True),
    )
    op.create_index('ix_comments_id', 'comments', ['id'])
    op.create_index('ix_comments_file_path', 'comments', ['file_path'])
    op.create_index('idx_comments_project_id', 'comments', ['project_id'])
    op.create_index('ix_comments_horizons_media_asset_id', 'comments', ['horizons_media_asset_id'])
    op.create_index('ix_comments_horizons_shot_version_id', 'comments', ['horizons_shot_version_id'])
    op.create_index('ix_comments_parent_comment_id', 'comments', ['parent_comment_id'])
    op.create_index('ix_comments_root_comment_id', 'comments', ['root_comment_id'])

    op.create_table(
        'shares',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('path', sa.String(), nullable=True),
        sa.Column('is_folder', sa.Boolean(), nullable=True),
        sa.Column('share_type', sa.String(), nullable=True),
        sa.Column('project_id', sa.String(), nullable=True),
        sa.Column('tracker_name', sa.String(), nullable=True),
        sa.Column('page_id', sa.String(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=True),
        sa.Column('expires_at', sa.Float(), nullable=True),
        sa.Column('password_hash', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('access_count', sa.Integer(), nullable=True),
        sa.Column('last_accessed', sa.Float(), nullable=True),
        sa.Column('allow_download', sa.Boolean(), nullable=True),
        sa.Column('allow_upload', sa.Boolean(), nullable=True),
        sa.Column('filter_assigned_to', sa.String(), nullable=True),
        sa.Column('hide_internal_fields', sa.Boolean(), nullable=True),
    )
    op.create_index('idx_shares_share_id', 'shares', ['id'])
    op.create_index('idx_shares_project_id', 'shares', ['project_id'])

    op.create_table(
        'transcodes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('output_path', sa.String(), nullable=True),
        sa.Column('progress', sa.Float(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=True),
    )
    op.create_index('ix_transcodes_file_path', 'transcodes', ['file_path'], unique=True)

    op.create_table(
        'activity_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('user_name', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('entity_title', sa.String(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=True),
    )
    op.create_index('idx_activity_log_created', 'activity_log', ['created_at'])

    op.create_table(
        'recently_viewed',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('item_id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('subtitle', sa.String(), nullable=True),
        sa.Column('viewed_at', sa.Float(), nullable=True),
    )
    op.create_index('idx_recently_viewed_user', 'recently_viewed', ['user_id'])
    op.create_index('idx_recently_viewed_time', 'recently_viewed', ['viewed_at'])

    op.create_table(
        'user_preferences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False, unique=True),
        sa.Column('mc_layout', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.Float(), nullable=True),
    )
    op.create_index('idx_user_prefs_user', 'user_preferences', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_user_prefs_user', table_name='user_preferences')
    op.drop_table('user_preferences')
    op.drop_index('idx_recently_viewed_time', table_name='recently_viewed')
    op.drop_index('idx_recently_viewed_user', table_name='recently_viewed')
    op.drop_table('recently_viewed')
    op.drop_index('idx_activity_log_created', table_name='activity_log')
    op.drop_table('activity_log')
    op.drop_index('ix_transcodes_file_path', table_name='transcodes')
    op.drop_table('transcodes')
    op.drop_index('idx_shares_project_id', table_name='shares')
    op.drop_index('idx_shares_share_id', table_name='shares')
    op.drop_table('shares')
    op.drop_index('ix_comments_root_comment_id', table_name='comments')
    op.drop_index('ix_comments_parent_comment_id', table_name='comments')
    op.drop_index('ix_comments_horizons_shot_version_id', table_name='comments')
    op.drop_index('ix_comments_horizons_media_asset_id', table_name='comments')
    op.drop_index('idx_comments_project_id', table_name='comments')
    op.drop_index('ix_comments_file_path', table_name='comments')
    op.drop_index('ix_comments_id', table_name='comments')
    op.drop_table('comments')
