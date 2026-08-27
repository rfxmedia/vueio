"""complete current model schema baseline

Revision ID: 20260713_0009
Revises: 20260713_0008
Create Date: 2026-07-13 20:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260713_0009'
down_revision = '20260713_0008'
branch_labels = None
depends_on = None


STALE_SHARE_COLUMNS = ('filter_assigned_to', 'hide_internal_fields')
# A database can lose its Alembic revision marker after later migrations have
# already added columns. Those known columns are safe during this historical
# adoption preflight; arbitrary extras still fail closed.
KNOWN_LATER_COLUMN_SPECS = {
    'horizons_projects': {
        'storage_root': ('string', False),
        'storage_path': ('string', True),
    },
    'horizons_shot_versions': {
        'share_state': ('string', False),
        'published_at': ('float', True),
    },
    'horizons_trackers': {'settings_json': ('text', True)},
    'media_assets': {'artifact_identity': ('string', True)},
    'shares': {'request_files': ('boolean', False)},
    'tracker_events': {
        'undo_of_event_id': ('integer', True),
        'state_snapshot': ('largebinary', True),
        'state_hash': ('string', True),
    },
    'transcodes': {'last_accessed': ('float', True)},
    'upload_sessions': {'owner_user_id': ('string', True)},
}
STALE_SHARE_COLUMN_SPECS = {
    'filter_assigned_to': ('string', True, None),
    'hide_internal_fields': ('boolean', True, None),
}
STALE_SHARE_AUDIT_TABLE = 'stale_share_field_retirement_audit'
STALE_SHARE_AUDIT_COLUMNS = (
    'migration_revision', 'share_id', 'field_name', 'source_dialect',
    'source_column_type', 'source_column_nullable', 'source_column_default',
    'value_type', 'value_text', 'value_integer', 'value_boolean',
    'evidence_created_at',
)

TABLE_SPECS = (
    ('activity_log', (('id', 'integer', False, True, None), ('user_id', 'string', False, False, None), ('user_name', 'string', False, False, None), ('action', 'string', False, False, None), ('entity_type', 'string', False, False, None), ('entity_id', 'string', False, False, None), ('entity_title', 'string', True, False, None), ('details', 'text', True, False, None), ('created_at', 'float', True, False, None)), (), ()),
    ('agent_api_keys', (('id', 'string', False, True, None), ('name', 'string', False, False, None), ('user_id', 'string', False, False, None), ('key_prefix', 'string', False, False, None), ('secret_hash', 'string', False, False, None), ('encrypted_token', 'text', True, False, None), ('scopes_json', 'text', False, False, '[]'), ('is_active', 'boolean', False, False, '1'), ('created_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None), ('last_used_at', 'float', True, False, None), ('revoked_at', 'float', True, False, None)), (), (('ix_agent_api_keys_key_prefix', ('key_prefix',), False), ('ix_agent_api_keys_secret_hash', ('secret_hash',), True), ('ix_agent_api_keys_user_id', ('user_id',), False))),
    ('agent_mutation_receipts', (('id', 'string', False, True, None), ('agent_key_id', 'string', False, False, None), ('operation', 'string', False, False, None), ('idempotency_key', 'string', False, False, None), ('response_json', 'text', False, False, None), ('created_at', 'float', True, False, None)), (('uq_agent_mutation_receipts_key_operation_idempotency', ('agent_key_id', 'operation', 'idempotency_key')),), (('ix_agent_mutation_receipts_agent_key_id', ('agent_key_id',), False), ('ix_agent_mutation_receipts_idempotency_key', ('idempotency_key',), False), ('ix_agent_mutation_receipts_operation', ('operation',), False))),
    ('app_identity', (('id', 'integer', False, True, None), ('team_name', 'string', False, False, 'Vue'), ('website_url', 'string', True, False, None), ('logo_upload_name', 'string', True, False, None), ('updated_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), ()),
    ('app_theme', (('id', 'integer', False, True, None), ('colors_json', 'text', False, False, '{}'), ('updated_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), ()),
    ('comments', (('id', 'integer', False, True, None), ('file_path', 'string', True, False, None), ('project_id', 'string', True, False, None), ('horizons_media_asset_id', 'string', True, False, None), ('horizons_shot_version_id', 'string', True, False, None), ('user_name', 'string', True, False, None), ('timestamp', 'float', True, False, None), ('text', 'text', True, False, None), ('resolved', 'boolean', True, False, '0'), ('created_at', 'float', True, False, None), ('parent_comment_id', 'integer', True, False, None), ('root_comment_id', 'integer', True, False, None), ('annotation_data', 'text', True, False, None), ('annotation_target', 'text', True, False, None), ('attachments_data', 'text', True, False, None)), (), (('ix_comments_file_path', ('file_path',), False), ('ix_comments_horizons_media_asset_id', ('horizons_media_asset_id',), False), ('ix_comments_horizons_shot_version_id', ('horizons_shot_version_id',), False), ('ix_comments_id', ('id',), False), ('ix_comments_parent_comment_id', ('parent_comment_id',), False), ('ix_comments_project_id', ('project_id',), False), ('ix_comments_root_comment_id', ('root_comment_id',), False))),
    ('download_events', (('id', 'string', False, True, None), ('created_at', 'float', True, False, None), ('user_id', 'string', True, False, None), ('user_name', 'string', True, False, None), ('source', 'string', False, False, 'app'), ('auth_mode', 'string', True, False, None), ('share_id', 'string', True, False, None), ('project_id', 'string', True, False, None), ('tracker_id', 'string', True, False, None), ('event_type', 'string', False, False, None), ('resource_type', 'string', False, False, None), ('resource_id', 'string', True, False, None), ('resource_name', 'string', True, False, None), ('filename', 'string', True, False, None), ('paths_json', 'text', False, False, '[]'), ('size_bytes', 'bigint', True, False, None), ('status', 'string', False, False, 'started'), ('ip_address', 'string', True, False, None), ('ip_chain_json', 'text', False, False, '{}'), ('geo_json', 'text', False, False, '{}'), ('device_json', 'text', False, False, '{}'), ('request_json', 'text', False, False, '{}'), ('client_json', 'text', False, False, '{}'), ('metadata_json', 'text', False, False, '{}')), (), (('ix_download_events_created_at', ('created_at',), False), ('ix_download_events_event_type', ('event_type',), False), ('ix_download_events_ip_address', ('ip_address',), False), ('ix_download_events_project_id', ('project_id',), False), ('ix_download_events_resource_type', ('resource_type',), False), ('ix_download_events_share_id', ('share_id',), False), ('ix_download_events_source', ('source',), False), ('ix_download_events_user_id', ('user_id',), False))),
    ('file_operation_journal', (('id', 'string', False, True, None), ('operation_type', 'string', False, False, None), ('project_id', 'string', False, False, None), ('source_path', 'string', True, False, None), ('destination_path', 'string', True, False, None), ('status', 'string', False, False, 'pending'), ('payload_json', 'text', False, False, '{}'), ('error_text', 'text', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), (('ix_file_operation_journal_operation_type', ('operation_type',), False), ('ix_file_operation_journal_project_id', ('project_id',), False), ('ix_file_operation_journal_status', ('status',), False))),
    ('horizons_pages', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('slug', 'string', False, False, None), ('title', 'string', False, False, None), ('description', 'text', True, False, None), ('cover_path', 'string', True, False, None), ('blocks_json', 'text', False, False, '[]'), ('created_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('idx_horizons_pages_project_slug', ('project_id', 'slug')),), (('ix_horizons_pages_project_id', ('project_id',), False), ('ix_horizons_pages_slug', ('slug',), False))),
    ('horizons_project_grants', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('subject_type', 'string', False, False, None), ('subject_id', 'string', False, False, None), ('role', 'string', False, False, 'viewer'), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('idx_horizons_grants_unique', ('project_id', 'subject_type', 'subject_id')),), (('ix_horizons_project_grants_project_id', ('project_id',), False), ('ix_horizons_project_grants_subject_id', ('subject_id',), False))),
    ('horizons_projects', (('id', 'string', False, True, None), ('slug', 'string', False, False, None), ('title', 'string', False, False, None), ('description', 'text', True, False, None), ('status', 'string', False, False, 'active'), ('visibility', 'string', False, False, 'private'), ('created_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None), ('due_date', 'string', True, False, None), ('thumbnail_path', 'string', True, False, None), ('project_tools_json', 'text', True, False, None)), (), (('ix_horizons_projects_slug', ('slug',), True),)),
    ('horizons_shot_assignees', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('tracker_id', 'string', False, False, None), ('shot_id', 'string', False, False, None), ('user_id', 'string', False, False, None), ('sort_order', 'integer', False, False, '0'), ('created_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('uq_horizon_shot_assignee_user', ('shot_id', 'user_id')),), (('ix_horizons_shot_assignees_project_id', ('project_id',), False), ('ix_horizons_shot_assignees_shot_id', ('shot_id',), False), ('ix_horizons_shot_assignees_tracker_id', ('tracker_id',), False), ('ix_horizons_shot_assignees_user_id', ('user_id',), False))),
    ('horizons_shot_versions', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('tracker_id', 'string', False, False, None), ('shot_id', 'string', False, False, None), ('label', 'string', False, False, None), ('media_asset_id', 'string', True, False, None), ('notes', 'text', True, False, None), ('created_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('idx_horizons_versions_shot_label', ('shot_id', 'label')),), (('ix_horizons_shot_versions_media_asset_id', ('media_asset_id',), False), ('ix_horizons_shot_versions_project_id', ('project_id',), False), ('ix_horizons_shot_versions_shot_id', ('shot_id',), False), ('ix_horizons_shot_versions_tracker_id', ('tracker_id',), False))),
    ('horizons_shots', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('tracker_id', 'string', False, False, None), ('shot_code', 'string', False, False, None), ('description', 'text', True, False, None), ('status', 'string', False, False, 'not_started'), ('category', 'string', True, False, None), ('assignee_user_id', 'string', True, False, None), ('latest_version_label', 'string', True, False, None), ('latest_media_asset_id', 'string', True, False, None), ('archived_at', 'float', True, False, None), ('archived_by', 'string', True, False, None), ('archive_reason', 'text', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('idx_horizons_shots_tracker_code', ('tracker_id', 'shot_code')),), (('ix_horizons_shots_archived_at', ('archived_at',), False), ('ix_horizons_shots_assignee_user_id', ('assignee_user_id',), False), ('ix_horizons_shots_latest_media_asset_id', ('latest_media_asset_id',), False), ('ix_horizons_shots_project_id', ('project_id',), False), ('ix_horizons_shots_shot_code', ('shot_code',), False), ('ix_horizons_shots_tracker_id', ('tracker_id',), False))),
    ('horizons_trackers', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('slug', 'string', False, False, None), ('name', 'string', False, False, None), ('tags_json', 'text', True, False, None), ('stats_json', 'text', True, False, None), ('stats_updated_at', 'float', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('idx_horizons_trackers_project_slug', ('project_id', 'slug')),), (('ix_horizons_trackers_project_id', ('project_id',), False), ('ix_horizons_trackers_slug', ('slug',), False))),
    ('media_assets', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('file_path', 'string', False, False, None), ('storage_scope', 'string', False, False, 'project'), ('content_hash', 'string', True, False, None), ('file_size', 'bigint', True, False, None), ('modified_at', 'float', True, False, None), ('source_signature', 'string', True, False, None), ('unavailable_at', 'float', True, False, None), ('unavailable_reason', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), (('ix_media_assets_project_id', ('project_id',), False), ('ix_media_assets_source_signature', ('source_signature',), False), ('ix_media_assets_unavailable_at', ('unavailable_at',), False))),
    ('media_metadata', (('cache_identity', 'string', False, True, None), ('media_asset_id', 'string', True, False, None), ('file_path', 'string', False, False, None), ('file_size', 'bigint', True, False, None), ('modified_at', 'float', True, False, None), ('info_json', 'text', False, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), (('ix_media_metadata_media_asset_id', ('media_asset_id',), False),)),
    ('notification_deliveries', (('id', 'string', False, True, None), ('tracker_event_id', 'integer', False, False, None), ('recipient_user_id', 'string', False, False, None), ('subscription_id', 'string', False, False, None), ('provider', 'string', False, False, None), ('status', 'string', False, False, 'pending'), ('attempts', 'integer', False, False, '0'), ('next_attempt_at', 'float', True, False, None), ('sent_at', 'float', True, False, None), ('last_error', 'text', True, False, None), ('payload_json', 'text', False, False, '{}'), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('uq_notification_delivery_event_subscription_recipient', ('tracker_event_id', 'subscription_id', 'recipient_user_id')),), (('ix_notification_deliveries_next_attempt_at', ('next_attempt_at',), False), ('ix_notification_deliveries_provider', ('provider',), False), ('ix_notification_deliveries_recipient_user_id', ('recipient_user_id',), False), ('ix_notification_deliveries_status', ('status',), False), ('ix_notification_deliveries_subscription_id', ('subscription_id',), False), ('ix_notification_deliveries_tracker_event_id', ('tracker_event_id',), False))),
    ('notification_preferences', (('user_id', 'string', False, True, None), ('default_scope', 'string', False, False, 'related_to_me'), ('event_types_json', 'text', False, False, '[]'), ('channels_json', 'text', False, False, '{}'), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), ()),
    ('notification_read_state', (('id', 'integer', False, True, None), ('user_id', 'string', False, False, None), ('feed_key', 'string', False, False, 'default'), ('last_seen_event_id', 'integer', True, False, None), ('last_seen_created_at', 'float', False, False, '0'), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (('uq_notification_read_state_user_feed', ('user_id', 'feed_key')),), (('ix_notification_read_state_user_id', ('user_id',), False),)),
    ('notification_subscriptions', (('id', 'string', False, True, None), ('provider', 'string', False, False, None), ('recipient_user_id', 'string', False, False, None), ('destination', 'string', False, False, None), ('scope', 'string', False, False, 'related_to_me'), ('project_filters_json', 'text', False, False, '[]'), ('event_filters_json', 'text', False, False, '[]'), ('config_json', 'text', False, False, '{}'), ('is_enabled', 'boolean', False, False, '1'), ('created_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), (('ix_notification_subscriptions_provider', ('provider',), False), ('ix_notification_subscriptions_recipient_user_id', ('recipient_user_id',), False))),
    ('recently_viewed', (('id', 'integer', False, True, None), ('user_id', 'string', False, False, None), ('item_type', 'string', False, False, None), ('item_id', 'string', False, False, None), ('project_id', 'string', True, False, None), ('title', 'string', True, False, None), ('subtitle', 'string', True, False, None), ('viewed_at', 'float', True, False, None)), (), (('ix_recently_viewed_user_id', ('user_id',), False),)),
    ('shares', (('id', 'string', False, True, None), ('path', 'string', True, False, None), ('is_folder', 'boolean', True, False, '0'), ('share_type', 'string', True, False, 'file'), ('project_id', 'string', True, False, None), ('tracker_id', 'string', True, False, None), ('tracker_name', 'string', True, False, None), ('page_id', 'string', True, False, None), ('media_asset_id', 'string', True, False, None), ('created_by', 'string', True, False, None), ('created_at', 'float', True, False, None), ('expires_at', 'float', True, False, None), ('password_hash', 'string', True, False, None), ('is_active', 'boolean', True, False, '1'), ('access_count', 'integer', True, False, '0'), ('last_accessed', 'float', True, False, None), ('allow_download', 'boolean', True, False, '0'), ('allow_upload', 'boolean', True, False, '0')), (), (('ix_shares_media_asset_id', ('media_asset_id',), False),)),
    ('shot_registry', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('tracker_id', 'string', True, False, None), ('tracker_name', 'string', False, False, None), ('shot_id', 'string', False, False, None), ('status', 'string', False, False, 'not_started'), ('description', 'text', True, False, None), ('category', 'string', True, False, None), ('latest_version_number', 'integer', True, False, None), ('latest_file_path', 'string', True, False, None), ('latest_media_asset_id', 'string', True, False, None), ('source', 'string', False, False, 'tracker_json'), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), (('ix_shot_registry_latest_media_asset_id', ('latest_media_asset_id',), False), ('ix_shot_registry_project_id', ('project_id',), False), ('ix_shot_registry_shot_id', ('shot_id',), False), ('ix_shot_registry_tracker_id', ('tracker_id',), False), ('ix_shot_registry_tracker_name', ('tracker_name',), False))),
    ('tracker_events', (('id', 'integer', False, True, None), ('project_id', 'string', False, False, None), ('tracker_id', 'string', False, False, None), ('shot_id', 'string', True, False, None), ('shot_version_id', 'string', True, False, None), ('comment_id', 'string', True, False, None), ('event_type', 'string', False, False, None), ('actor_id', 'string', True, False, None), ('actor_name', 'string', False, False, None), ('source', 'string', False, False, 'app'), ('payload_json', 'text', True, False, None), ('created_at', 'float', True, False, None)), (), (('ix_tracker_events_comment_id', ('comment_id',), False), ('ix_tracker_events_created_at', ('created_at',), False), ('ix_tracker_events_event_type', ('event_type',), False), ('ix_tracker_events_project_id', ('project_id',), False), ('ix_tracker_events_shot_id', ('shot_id',), False), ('ix_tracker_events_shot_version_id', ('shot_version_id',), False), ('ix_tracker_events_tracker_id', ('tracker_id',), False))),
    ('transcodes', (('id', 'integer', False, True, None), ('file_path', 'string', True, False, None), ('status', 'string', True, False, 'pending'), ('output_path', 'string', True, False, None), ('progress', 'float', True, False, '0'), ('duration', 'float', True, False, '0'), ('created_at', 'float', True, False, None)), (), (('ix_transcodes_file_path', ('file_path',), True),)),
    ('upload_items', (('id', 'string', False, True, None), ('session_id', 'string', False, False, None), ('rel_path', 'string', False, False, None), ('original_name', 'string', False, False, None), ('mime_type', 'string', True, False, None), ('size_bytes', 'bigint', False, False, '0'), ('bytes_received', 'bigint', False, False, '0'), ('temp_path', 'string', True, False, None), ('final_path', 'string', True, False, None), ('status', 'string', False, False, 'pending'), ('error_text', 'text', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None), ('completed_at', 'float', True, False, None)), (), (('ix_upload_items_completed_at', ('completed_at',), False), ('ix_upload_items_final_path', ('final_path',), False), ('ix_upload_items_session_id', ('session_id',), False))),
    ('upload_sessions', (('id', 'string', False, True, None), ('scope_type', 'string', False, False, None), ('share_id', 'string', True, False, None), ('project_id', 'string', True, False, None), ('base_path', 'string', False, False, ''), ('uploader_name', 'string', False, False, None), ('client_batch_id', 'string', False, False, None), ('status', 'string', False, False, 'active'), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None), ('last_activity_at', 'float', True, False, None), ('expires_at', 'float', True, False, None)), (), (('ix_upload_sessions_client_batch_id', ('client_batch_id',), False), ('ix_upload_sessions_expires_at', ('expires_at',), False), ('ix_upload_sessions_project_id', ('project_id',), False), ('ix_upload_sessions_scope_type', ('scope_type',), False), ('ix_upload_sessions_share_id', ('share_id',), False))),
    ('user_preferences', (('id', 'integer', False, True, None), ('user_id', 'string', False, False, None), ('mc_layout', 'text', True, False, None), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), (('ix_user_preferences_user_id', ('user_id',), True),)),
    ('user_sessions', (('id', 'string', False, True, None), ('user_id', 'string', False, False, None), ('created_at', 'float', True, False, None), ('last_accessed', 'float', True, False, None), ('expires_at', 'float', False, False, None)), (), (('ix_user_sessions_expires_at', ('expires_at',), False), ('ix_user_sessions_user_id', ('user_id',), False))),
    ('version_registry', (('id', 'string', False, True, None), ('project_id', 'string', False, False, None), ('tracker_id', 'string', True, False, None), ('tracker_name', 'string', False, False, None), ('shot_id', 'string', False, False, None), ('variant_id', 'string', True, False, None), ('version_number', 'integer', False, False, None), ('file_path', 'string', False, False, None), ('media_asset_id', 'string', True, False, None), ('source', 'string', False, False, 'tracker_json'), ('created_at', 'float', True, False, None), ('updated_at', 'float', True, False, None)), (), (('ix_version_registry_media_asset_id', ('media_asset_id',), False), ('ix_version_registry_project_id', ('project_id',), False), ('ix_version_registry_shot_id', ('shot_id',), False), ('ix_version_registry_tracker_name', ('tracker_name',), False), ('ix_version_registry_variant_id', ('variant_id',), False))),
)

AUDIT_SPEC = ('media_asset_duplicate_retire_audit', (('id', 'integer', False, True, None), ('migration_revision', 'string', False, False, None), ('media_asset_id', 'string', False, False, None), ('previous_unavailable_at', 'float', True, False, None), ('previous_unavailable_reason', 'string', True, False, None), ('previous_updated_at', 'float', True, False, None), ('created_at', 'float', False, False, None)), (), ())
STALE_SHARE_AUDIT_SPEC = (
    STALE_SHARE_AUDIT_TABLE,
    (
        ('id', 'integer', False, True, None),
        ('migration_revision', 'string', False, False, None),
        ('share_id', 'string', False, False, None),
        ('field_name', 'string', False, False, None),
        ('source_dialect', 'string', False, False, None),
        ('source_column_type', 'string', False, False, None),
        ('source_column_nullable', 'boolean', False, False, None),
        ('source_column_default', 'text', True, False, None),
        ('value_type', 'string', False, False, None),
        ('value_text', 'text', True, False, None),
        ('value_integer', 'bigint', True, False, None),
        ('value_boolean', 'boolean', True, False, None),
        ('evidence_created_at', 'float', False, False, None),
    ),
    (('uq_stale_share_field_retirement', ('migration_revision', 'share_id', 'field_name')),),
    (('ix_stale_share_field_retirement_share_id', ('share_id',), False),),
)
AUDIT_SPECS = (AUDIT_SPEC, STALE_SHARE_AUDIT_SPEC)
TYPE_MAP = {
    'bigint': sa.BigInteger,
    'boolean': sa.Boolean,
    'float': sa.Float,
    'integer': sa.Integer,
    'largebinary': sa.LargeBinary,
    'string': sa.String,
    'text': sa.Text,
}
HISTORICAL_FINAL_ORDERS = {
    'comments': (
        (
            'id', 'file_path', 'project_id', 'horizons_media_asset_id',
            'horizons_shot_version_id', 'user_name', 'timestamp', 'text',
            'resolved', 'created_at', 'parent_comment_id', 'root_comment_id',
            'annotation_data', 'attachments_data', 'annotation_target',
        ),
        (
            'id', 'file_path', 'user_name', 'timestamp', 'text', 'resolved',
            'created_at', 'project_id', 'annotation_data', 'annotation_target',
            'attachments_data', 'horizons_media_asset_id',
            'horizons_shot_version_id', 'parent_comment_id', 'root_comment_id',
        ),
    ),
    'media_assets': (
        (
            'id', 'project_id', 'file_path', 'storage_scope', 'content_hash',
            'file_size', 'modified_at', 'created_at', 'updated_at',
            'source_signature', 'unavailable_at', 'unavailable_reason',
        ),
    ),
    'horizons_shots': (
        (
            'id', 'project_id', 'tracker_id', 'shot_code', 'description',
            'status', 'category', 'assignee_user_id', 'latest_version_label',
            'latest_media_asset_id', 'created_at', 'updated_at', 'archived_at',
            'archived_by', 'archive_reason',
        ),
    ),
    'shares': (
        (
            'id', 'path', 'is_folder', 'share_type', 'project_id',
            'tracker_name', 'page_id', 'created_by', 'created_at',
            'expires_at', 'password_hash', 'is_active', 'access_count',
            'last_accessed', 'allow_download', 'allow_upload', 'tracker_id',
            'media_asset_id',
        ),
        (
            'id', 'path', 'is_folder', 'share_type', 'project_id',
            'tracker_id', 'tracker_name', 'page_id', 'created_by',
            'created_at', 'expires_at', 'password_hash', 'is_active',
            'access_count', 'last_accessed', 'allow_download',
            'allow_upload', 'media_asset_id',
        ),
    ),
}
DIALECT_HISTORICAL_FINAL_ORDERS = {
    'sqlite': {
        'comments': ((
            'id', 'file_path', 'user_name', 'timestamp', 'text', 'resolved', 'created_at', 'annotation_data', 'attachments_data', 'project_id', 'horizons_media_asset_id', 'horizons_shot_version_id', 'parent_comment_id', 'root_comment_id', 'annotation_target',
        ),),
        'agent_api_keys': (
            (
                'id', 'name', 'user_id', 'key_prefix', 'secret_hash',
                'scopes_json', 'is_active', 'created_by', 'created_at',
                'updated_at', 'last_used_at', 'revoked_at',
                'encrypted_token',
            ),
        ),
        'horizons_shots': (
            (
                'id', 'project_id', 'tracker_id', 'shot_code',
                'description', 'status', 'category', 'latest_version_label',
                'latest_media_asset_id', 'created_at', 'updated_at',
                'assignee_user_id', 'archived_at', 'archived_by',
                'archive_reason',
            ),
        ),
        'horizons_trackers': (
            (
                'id', 'project_id', 'slug', 'name', 'created_at',
                'updated_at', 'stats_json', 'stats_updated_at', 'tags_json',
            ),
        ),
        'shares': ((
            'id', 'path', 'is_folder', 'share_type', 'project_id', 'created_by', 'created_at', 'expires_at', 'password_hash', 'is_active', 'access_count', 'last_accessed', 'allow_download', 'tracker_name', 'allow_upload', 'page_id', 'tracker_id', 'media_asset_id',
        ), (
            'id', 'path', 'is_folder', 'share_type', 'project_id', 'created_by', 'created_at', 'expires_at', 'password_hash', 'is_active', 'access_count', 'last_accessed', 'allow_download', 'tracker_name', 'allow_upload', 'page_id', 'media_asset_id', 'tracker_id',
        ),),
        'shot_registry': ((
            'id', 'project_id', 'tracker_name', 'shot_id', 'status', 'description', 'category', 'latest_version_number', 'latest_file_path', 'latest_media_asset_id', 'source', 'created_at', 'updated_at', 'tracker_id',
        ),),
        'version_registry': ((
            'id', 'project_id', 'tracker_name', 'shot_id', 'variant_id', 'version_number', 'file_path', 'media_asset_id', 'source', 'created_at', 'updated_at', 'tracker_id',
        ),),
    },
    'postgresql': {
        'horizons_trackers': (
            (
                'id', 'project_id', 'slug', 'name', 'stats_json',
                'stats_updated_at', 'created_at', 'updated_at',
                'tags_json',
            ),
        ),
        'shot_registry': (
            (
                'id', 'project_id', 'tracker_name', 'shot_id', 'status',
                'description', 'category', 'latest_version_number',
                'latest_file_path', 'latest_media_asset_id', 'source',
                'created_at', 'updated_at', 'tracker_id',
            ),
        ),
        'version_registry': (
            (
                'id', 'project_id', 'tracker_name', 'shot_id', 'variant_id',
                'version_number', 'file_path', 'media_asset_id', 'source',
                'created_at', 'updated_at', 'tracker_id',
            ),
        ),
    },
}
DIALECT_HISTORICAL_MISSING_UNIQUES = {
    'sqlite': {
        'agent_mutation_receipts': (
            ('agent_key_id', 'operation', 'idempotency_key'),
        ),
        'horizons_pages': (('project_id', 'slug'),),
        'horizons_project_grants': (
            ('project_id', 'subject_type', 'subject_id'),
        ),
        'horizons_shot_versions': (('shot_id', 'label'),),
        'horizons_shots': (('tracker_id', 'shot_code'),),
        'horizons_trackers': (('project_id', 'slug'),),
    },
}
HISTORICAL_SERVER_DEFAULTS = {
    'agent_api_keys': {'scopes_json': {'[]'}, 'is_active': {'1', 'true'}},
    'app_identity': {'team_name': {'Vue'}},
    'app_theme': {'colors_json': {'{}'}},
    'download_events': {
        'source': {'app'}, 'paths_json': {'[]'}, 'status': {'started'},
        'ip_chain_json': {'{}'}, 'geo_json': {'{}'}, 'device_json': {'{}'},
        'request_json': {'{}'}, 'client_json': {'{}'}, 'metadata_json': {'{}'},
    },
    'file_operation_journal': {'status': {'pending'}, 'payload_json': {'{}'}},
    'horizons_pages': {'blocks_json': {'[]'}},
    'horizons_project_grants': {'role': {'viewer'}},
    'horizons_projects': {'status': {'active'}, 'visibility': {'private'}, 'storage_root': {'data'}},
    'horizons_shot_versions': {'share_state': {'published'}},
    'horizons_shot_assignees': {'sort_order': {'0'}},
    'horizons_shots': {'status': {'not_started'}},
    'media_assets': {'storage_scope': {'project'}},
    'notification_deliveries': {'status': {'pending'}, 'attempts': {'0'}, 'payload_json': {'{}'}},
    'notification_preferences': {'default_scope': {'related_to_me'}, 'event_types_json': {'[]'}, 'channels_json': {'{}'}},
    'notification_read_state': {'feed_key': {'default'}, 'last_seen_created_at': {'0'}},
    'notification_subscriptions': {
        'scope': {'related_to_me'}, 'project_filters_json': {'[]'},
        'event_filters_json': {'[]'}, 'config_json': {'{}'}, 'is_enabled': {'1', 'true'},
    },
    'shares': {
        'allow_download': {'0', 'false'},
        'allow_upload': {'0', 'false'},
        'request_files': {'0', 'false'},
    },
    'shot_registry': {'status': {'not_started'}, 'source': {'tracker_json'}},
    'tracker_events': {'source': {'app'}},
    'upload_items': {'size_bytes': {'0'}, 'bytes_received': {'0'}, 'status': {'pending'}},
    'upload_sessions': {'base_path': {''}, 'status': {'active'}},
    'version_registry': {'source': {'tracker_json'}},
}


def _ident(value: str) -> str:
    if not value.replace('_', '').isalnum():
        raise ValueError(f'Unsafe SQL identifier: {value!r}')
    return value


def _q(value: str) -> str:
    return f'"{_ident(value)}"'


def _metadata_for(specs=TABLE_SPECS) -> sa.MetaData:
    metadata = sa.MetaData()
    for table_name, columns, uniques, indexes in specs:
        table_columns = [
            sa.Column(name, TYPE_MAP[type_key](), primary_key=pk, nullable=nullable)
            for name, type_key, nullable, pk, _default in columns
        ]
        constraints = [sa.UniqueConstraint(*cols, name=name) for name, cols in uniques]
        table = sa.Table(table_name, metadata, *table_columns, *constraints)
        for name, cols, unique in indexes:
            sa.Index(name, *(table.c[col] for col in cols), unique=unique)
    return metadata


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table_name: str) -> dict[str, dict]:
    return {column['name']: column for column in sa.inspect(bind).get_columns(table_name)}


def _row_count(bind, table_name: str) -> int:
    return bind.execute(sa.text(f'SELECT COUNT(*) FROM {_q(table_name)}')).scalar() or 0


def _column_for(name: str, type_key: str, nullable: bool, pk: bool, _default: str | None) -> sa.Column:
    return sa.Column(name, TYPE_MAP[type_key](), primary_key=pk, nullable=nullable)


def _type_matches(actual: sa.types.TypeEngine, type_key: str) -> bool:
    expected = TYPE_MAP[type_key]()
    return actual._type_affinity is expected._type_affinity


def _strip_wrapping_parentheses(value: str) -> str:
    while value.startswith('(') and value.endswith(')'):
        depth = 0
        wraps = True
        for index, char in enumerate(value):
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    wraps = False
                    break
        if not wraps:
            break
        value = value[1:-1].strip()
    return value


def _normalize_default(actual: object) -> tuple[str, bool]:
    value = _strip_wrapping_parentheses(str(actual).strip()).split('::', 1)[0].strip()
    value = _strip_wrapping_parentheses(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1], True
    if value.lower() in {'false', 'true', 'null'}:
        return value.lower(), False
    return value, False


def _default_matches(table_name: str, column_name: str, actual: object) -> bool:
    if actual is None:
        return True
    normalized, quoted = _normalize_default(actual)
    if not quoted and normalized == 'null':
        return True
    return normalized in HISTORICAL_SERVER_DEFAULTS.get(table_name, {}).get(column_name, set())


def _has_unique(inspector, table_name: str, columns: tuple[str, ...]) -> bool:
    wanted = list(columns)
    for constraint in inspector.get_unique_constraints(table_name):
        if constraint.get('column_names') == wanted:
            return True
    for index in inspector.get_indexes(table_name):
        if index.get('unique') and index.get('column_names') == wanted:
            return True
    return False


def _unique_shapes(inspector, table_name: str) -> set[tuple[str, ...]]:
    shapes = {
        tuple(item.get('column_names') or ())
        for item in inspector.get_unique_constraints(table_name)
    }
    shapes.update(
        tuple(item.get('column_names') or ())
        for item in inspector.get_indexes(table_name)
        if item.get('unique')
    )
    return shapes


def _can_defer_historical_unique(
    bind,
    table_name: str,
    columns: tuple[str, ...],
    adopted_order: tuple[str, ...],
    expected_order: tuple[str, ...],
) -> bool:
    deferred = DIALECT_HISTORICAL_MISSING_UNIQUES.get(bind.dialect.name, {}).get(table_name, ())
    dialect_orders = DIALECT_HISTORICAL_FINAL_ORDERS.get(bind.dialect.name, {}).get(table_name, ())
    return columns in deferred and adopted_order in {expected_order, *dialect_orders}


def _has_duplicate_groups(bind, table_name: str, columns: tuple[str, ...]) -> bool:
    grouped = ', '.join(_q(column) for column in columns)
    return bind.execute(sa.text(
        f'SELECT 1 FROM {_q(table_name)} GROUP BY {grouped} HAVING COUNT(*) > 1 LIMIT 1'
    )).first() is not None


def _accepted_complete_orders(table_name: str, expected_names: list[str], dialect_name: str) -> set[tuple[str, ...]]:
    dialect_orders = DIALECT_HISTORICAL_FINAL_ORDERS.get(dialect_name, {}).get(table_name, ())
    return {tuple(expected_names), *HISTORICAL_FINAL_ORDERS.get(table_name, ()), *dialect_orders}


def _allowed_extra_columns(table_name: str) -> set[str]:
    allowed = set(KNOWN_LATER_COLUMN_SPECS.get(table_name, ()))
    if table_name == 'shares':
        allowed.update(STALE_SHARE_COLUMNS)
    return allowed


def _default_value(default: str) -> object:
    if default in {'0', '1'}:
        return int(default)
    return default


def _missing_column_specs(bind, table_name: str, columns, existing: dict[str, dict]) -> list[tuple]:
    row_count = _row_count(bind, table_name)
    missing = []
    for spec in columns:
        name, _type_key, nullable, is_pk, default = spec
        if name in existing:
            continue
        if is_pk:
            raise RuntimeError(f'Cannot safely adopt {table_name}: missing primary key column {name}')
        if row_count and not nullable and default is None:
            raise RuntimeError(f'Cannot safely add non-null column {table_name}.{name} to a table with existing rows')
        missing.append(spec)
    return missing


def _validate_present_table(bind, spec) -> None:
    inspector = sa.inspect(bind)
    table_name, columns, uniques, indexes = spec
    existing = _columns(bind, table_name)
    expected_names = [column[0] for column in columns]
    extra = [name for name in existing if name not in expected_names and name not in _allowed_extra_columns(table_name)]
    if extra:
        raise RuntimeError(f'Cannot safely adopt {table_name}: unknown columns {",".join(extra)}')
    pk = inspector.get_pk_constraint(table_name).get('constrained_columns') or []
    expected_pk = [name for name, _type_key, _nullable, is_pk, _default in columns if is_pk]
    if pk != expected_pk:
        raise RuntimeError(f'Cannot safely adopt {table_name}: primary key {pk} != {expected_pk}')
    present_order = [name for name in existing if name in expected_names]
    missing = _missing_column_specs(bind, table_name, columns, existing)
    if missing:
        final_order = tuple(present_order + [item[0] for item in missing])
        if final_order not in _accepted_complete_orders(table_name, expected_names, bind.dialect.name):
            raise RuntimeError(f'Cannot safely repair {table_name}: partial columns are not an accepted prefix')
    elif tuple(present_order) not in _accepted_complete_orders(table_name, expected_names, bind.dialect.name):
        raise RuntimeError(f'Cannot safely adopt {table_name}: model columns are out of order')
    adopted_order = final_order if missing else tuple(present_order)
    for name, type_key, nullable, is_pk, default in columns:
        if name not in existing:
            continue
        actual = existing[name]
        if not _type_matches(actual['type'], type_key):
            raise RuntimeError(f'Cannot safely adopt {table_name}.{name}: incompatible type {actual["type"]!s}')
        if actual['nullable'] != nullable and not (is_pk and bind.dialect.name == 'sqlite'):
            raise RuntimeError(f'Cannot safely adopt {table_name}.{name}: incompatible nullability')
        if not is_pk and not _default_matches(table_name, name, actual.get('default')):
            raise RuntimeError(f'Cannot safely adopt {table_name}.{name}: incompatible server default')
    for name, (type_key, nullable) in KNOWN_LATER_COLUMN_SPECS.get(table_name, {}).items():
        if name not in existing:
            continue
        actual = existing[name]
        if not _type_matches(actual['type'], type_key):
            raise RuntimeError(f'Cannot safely adopt {table_name}.{name}: incompatible type {actual["type"]!s}')
        if actual['nullable'] != nullable:
            raise RuntimeError(f'Cannot safely adopt {table_name}.{name}: incompatible nullability')
        if not _default_matches(table_name, name, actual.get('default')):
            raise RuntimeError(f'Cannot safely adopt {table_name}.{name}: incompatible server default')
    for _name, cols in uniques:
        if not _has_unique(inspector, table_name, cols):
            if not _can_defer_historical_unique(
                bind, table_name, cols, adopted_order, tuple(expected_names)
            ):
                raise RuntimeError(f'Cannot safely adopt {table_name}: missing unique constraint on {",".join(cols)}')
            if _unique_shapes(inspector, table_name):
                raise RuntimeError(f'Cannot safely adopt {table_name}: incompatible historical unique shape')
            if _has_duplicate_groups(bind, table_name, cols):
                raise RuntimeError(f'Cannot safely adopt {table_name}: duplicate values for deferred unique constraint')
    for _name, cols, unique in indexes:
        if unique and not _has_unique(inspector, table_name, cols):
            raise RuntimeError(f'Cannot safely adopt {table_name}: missing unique index on {",".join(cols)}')


def _stale_share_value_plan(bind) -> list[dict[str, object]]:
    if 'shares' not in _tables(bind):
        return []
    share_columns = _columns(bind, 'shares')
    evidence: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for name in STALE_SHARE_COLUMNS:
        if name not in share_columns:
            continue
        column = share_columns[name]
        if not _type_matches(column['type'], STALE_SHARE_COLUMN_SPECS[name][0]):
            raise RuntimeError(f'Cannot retire stale shares.{name}: incompatible type {column["type"]!s}')
        if bind.dialect.name == 'sqlite':
            rows = bind.execute(sa.text(f"""
                SELECT id, {_q(name)} AS value, typeof({_q(name)}) AS value_type,
                       CAST({_q(name)} AS TEXT) AS value_text
                FROM shares
                WHERE {_q(name)} IS NOT NULL
                ORDER BY id
            """)).mappings().all()
        else:
            value_type = 'boolean' if name == 'hide_internal_fields' else 'text'
            rows = bind.execute(sa.text(f"""
                SELECT id, {_q(name)} AS value, CAST({_q(name)} AS TEXT) AS value_text
                FROM shares
                WHERE {_q(name)} IS NOT NULL
                ORDER BY id
            """)).mappings().all()
            rows = [dict(row, value_type=value_type) for row in rows]
        for row in rows:
            key = (row['id'], name)
            if key in seen:
                raise RuntimeError(f'Duplicate stale share evidence for {row["id"]}.{name}')
            seen.add(key)
            evidence.append(_stale_share_evidence_row(bind, column, name, row))
    return evidence


def _stale_share_evidence_row(bind, column: dict, field_name: str, row) -> dict[str, object]:
    value_type = row['value_type']
    value = row['value']
    value_text = row['value_text']
    value_integer = None
    value_boolean = None
    if field_name == 'filter_assigned_to':
        if value_type != 'text' or not isinstance(value, str):
            raise RuntimeError(f'Cannot represent stale shares.{field_name} value for {row["id"]}')
    elif bind.dialect.name == 'sqlite':
        if value_type != 'integer' or value not in (0, 1):
            raise RuntimeError(f'Cannot represent stale shares.{field_name} value for {row["id"]}')
        value_integer = int(value)
    elif isinstance(value, bool):
        value_boolean = value
    else:
        raise RuntimeError(f'Cannot represent stale shares.{field_name} value for {row["id"]}')
    return {
        'migration_revision': revision,
        'share_id': row['id'],
        'field_name': field_name,
        'source_dialect': bind.dialect.name,
        'source_column_type': str(column['type']),
        'source_column_nullable': bool(column['nullable']),
        'source_column_default': None if column.get('default') is None else str(column.get('default')),
        'value_type': value_type,
        'value_text': value_text,
        'value_integer': value_integer,
        'value_boolean': value_boolean,
        'evidence_created_at': 0.0,
    }


def _archive_stale_share_values(bind, evidence: list[dict[str, object]]) -> None:
    if not evidence:
        return
    for row in evidence:
        existing = bind.execute(
            sa.text(f"""
                SELECT migration_revision, share_id, field_name, source_dialect,
                       source_column_type, source_column_nullable, source_column_default,
                       value_type, value_text, value_integer, value_boolean,
                       evidence_created_at
                FROM {STALE_SHARE_AUDIT_TABLE}
                WHERE migration_revision = :migration_revision
                  AND share_id = :share_id
                  AND field_name = :field_name
            """),
            row,
        ).mappings().first()
        comparable = {key: row[key] for key in row}
        if existing is not None:
            if dict(existing) != comparable:
                raise RuntimeError(f'Conflicting stale share evidence for {row["share_id"]}.{row["field_name"]}')
            continue
        bind.execute(sa.text(f"""
            INSERT INTO {STALE_SHARE_AUDIT_TABLE} (
                migration_revision, share_id, field_name, source_dialect,
                source_column_type, source_column_nullable, source_column_default,
                value_type, value_text, value_integer, value_boolean,
                evidence_created_at
            ) VALUES (
                :migration_revision, :share_id, :field_name, :source_dialect,
                :source_column_type, :source_column_nullable, :source_column_default,
                :value_type, :value_text, :value_integer, :value_boolean,
                :evidence_created_at
            )
        """), row)


def _stale_share_evidence_key(row) -> tuple[object, object, object]:
    return row['migration_revision'], row['share_id'], row['field_name']


def _validate_existing_stale_share_evidence(bind, evidence: list[dict[str, object]]) -> None:
    if STALE_SHARE_AUDIT_TABLE not in _tables(bind):
        return
    expected = {_stale_share_evidence_key(row): row for row in evidence}
    rows = bind.execute(sa.text(f"""
        SELECT {', '.join(STALE_SHARE_AUDIT_COLUMNS)}
        FROM {STALE_SHARE_AUDIT_TABLE}
        ORDER BY migration_revision, share_id, field_name, id
    """)).mappings().all()
    seen: set[tuple[object, object, object]] = set()
    for row in rows:
        current = dict(row)
        key = _stale_share_evidence_key(current)
        if key in seen:
            raise RuntimeError('Duplicate stale share retirement evidence')
        seen.add(key)
        if current['migration_revision'] != revision:
            raise RuntimeError('Wrong-revision stale share retirement evidence')
        if current['field_name'] not in STALE_SHARE_COLUMNS:
            raise RuntimeError('Wrong-field stale share retirement evidence')
        if current['source_dialect'] != bind.dialect.name:
            raise RuntimeError('Wrong-dialect stale share retirement evidence')
        expected_row = expected.get(key)
        if expected_row is None:
            known_share = bind.execute(
                sa.text('SELECT COUNT(*) FROM shares WHERE id = :id'),
                {'id': current['share_id']},
            ).scalar() if 'shares' in _tables(bind) else 0
            reason = 'Injected extra' if known_share else 'Unknown-share'
            raise RuntimeError(f'{reason} stale share retirement evidence')
        if current != expected_row:
            raise RuntimeError(
                f'Conflicting stale share evidence for {current["share_id"]}.{current["field_name"]}'
            )
    missing = set(expected) - seen
    if missing:
        raise RuntimeError('Missing planned stale share retirement evidence')


def _preflight(bind, evidence: list[dict[str, object]]) -> None:
    existing_tables = _tables(bind)
    for spec in TABLE_SPECS + AUDIT_SPECS:
        if spec[0] in existing_tables:
            _validate_present_table(bind, spec)
    _validate_existing_stale_share_evidence(bind, evidence)


def _create_missing_tables(bind) -> None:
    metadata = _metadata_for(TABLE_SPECS + AUDIT_SPECS)
    existing_tables = _tables(bind)
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            table.create(bind=bind, checkfirst=True)


def _add_missing_columns(bind) -> None:
    for table_name, columns, _uniques, _indexes in TABLE_SPECS:
        if table_name not in _tables(bind):
            continue
        existing = _columns(bind, table_name)
        missing = _missing_column_specs(bind, table_name, columns, existing)
        if not missing:
            continue
        row_count = _row_count(bind, table_name)
        if bind.dialect.name == 'sqlite':
            with op.batch_alter_table(
                table_name,
                recreate='always',
                partial_reordering=(tuple(column[0] for column in columns),),
            ) as batch_op:
                for name, type_key, nullable, pk, default in missing:
                    add_nullable = nullable or (row_count > 0 and default is not None)
                    batch_op.add_column(_column_for(name, type_key, add_nullable, pk, default))
            _backfill_missing_defaults(bind, table_name, missing)
            not_null_backfills = [item for item in missing if row_count > 0 and not item[2] and item[4] is not None]
            if not_null_backfills:
                with op.batch_alter_table(table_name, recreate='always') as batch_op:
                    for name, type_key, _nullable, _pk, _default in not_null_backfills:
                        batch_op.alter_column(name, nullable=False, existing_type=TYPE_MAP[type_key]())
        else:
            for name, type_key, nullable, pk, default in missing:
                add_nullable = nullable or (row_count > 0 and default is not None)
                op.add_column(table_name, _column_for(name, type_key, add_nullable, pk, default))
            _backfill_missing_defaults(bind, table_name, missing)
            for name, type_key, nullable, _pk, default in missing:
                if not nullable:
                    op.alter_column(table_name, name, nullable=False, existing_type=TYPE_MAP[type_key]())


def _backfill_missing_defaults(bind, table_name: str, missing: list[tuple]) -> None:
    for name, _type_key, nullable, _pk, default in missing:
        if nullable or default is None:
            continue
        bind.execute(
            sa.text(f'UPDATE {_q(table_name)} SET {_q(name)} = :value WHERE {_q(name)} IS NULL'),
            {'value': _default_value(default)},
        )


def _postvalidate(bind) -> None:
    existing_tables = _tables(bind)
    for spec in TABLE_SPECS + AUDIT_SPECS:
        if spec[0] not in existing_tables:
            raise RuntimeError(f'0009 post-validation missing table {spec[0]}')
        _validate_present_table(bind, spec)
    stale_present = set(STALE_SHARE_COLUMNS).intersection(_columns(bind, 'shares'))
    if stale_present:
        raise RuntimeError(f'0009 post-validation stale shares columns remain: {",".join(sorted(stale_present))}')


def _drop_null_only_stale_share_columns(bind) -> None:
    if 'shares' not in _tables(bind):
        return
    share_columns = _columns(bind, 'shares')
    stale_present = [name for name in STALE_SHARE_COLUMNS if name in share_columns]
    if not stale_present:
        return
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('shares') as batch_op:
            for name in stale_present:
                batch_op.drop_column(name)
    else:
        for name in stale_present:
            op.drop_column('shares', name)


def _add_stale_share_columns_for_downgrade(bind) -> None:
    if 'shares' not in _tables(bind):
        return
    existing = _columns(bind, 'shares')
    missing = [name for name in STALE_SHARE_COLUMNS if name not in existing]
    if not missing:
        return
    if bind.dialect.name == 'sqlite':
        with op.batch_alter_table('shares') as batch_op:
            for name in missing:
                type_key, nullable, default = STALE_SHARE_COLUMN_SPECS[name]
                batch_op.add_column(_column_for(name, type_key, nullable, False, default))
    else:
        for name in missing:
            type_key, nullable, default = STALE_SHARE_COLUMN_SPECS[name]
            op.add_column('shares', _column_for(name, type_key, nullable, False, default))


def _stale_share_restore_rows(bind) -> list[dict[str, object]]:
    if STALE_SHARE_AUDIT_TABLE not in _tables(bind):
        return []
    _validate_present_table(bind, STALE_SHARE_AUDIT_SPEC)
    rows = bind.execute(sa.text(f"""
        SELECT share_id, field_name, source_dialect, value_type, value_text,
               value_integer, value_boolean
        FROM {STALE_SHARE_AUDIT_TABLE}
        WHERE migration_revision = :revision
        ORDER BY share_id, field_name
    """), {'revision': revision}).mappings().all()
    seen: set[tuple[str, str]] = set()
    restored: list[dict[str, object]] = []
    for row in rows:
        key = (row['share_id'], row['field_name'])
        if key in seen or row['field_name'] not in STALE_SHARE_COLUMNS:
            raise RuntimeError('Malformed stale share retirement evidence')
        seen.add(key)
        restored.append(_restore_value_from_evidence(row))
    return restored


def _restore_value_from_evidence(row) -> dict[str, object]:
    field_name = row['field_name']
    value = None
    if field_name == 'filter_assigned_to':
        if row['value_type'] != 'text' or row['value_text'] is None:
            raise RuntimeError('Malformed stale share retirement evidence')
        value = row['value_text']
    elif row['source_dialect'] == 'sqlite':
        if row['value_type'] != 'integer' or row['value_integer'] not in (0, 1):
            raise RuntimeError('Malformed stale share retirement evidence')
        value = row['value_integer']
    elif row['value_type'] == 'boolean' and row['value_boolean'] is not None:
        value = row['value_boolean']
    else:
        raise RuntimeError('Malformed stale share retirement evidence')
    return {'share_id': row['share_id'], 'field_name': field_name, 'value': value}


def _restore_stale_share_values(bind, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    missing_ids = [
        row['share_id'] for row in rows
        if bind.execute(sa.text('SELECT COUNT(*) FROM shares WHERE id = :id'), {'id': row['share_id']}).scalar() != 1
    ]
    if missing_ids:
        raise RuntimeError(f'Stale share evidence references missing shares: {",".join(sorted(set(missing_ids)))}')
    for name in STALE_SHARE_COLUMNS:
        occupied = bind.execute(sa.text(f'SELECT COUNT(*) FROM shares WHERE {_q(name)} IS NOT NULL')).scalar() or 0
        if occupied:
            raise RuntimeError(f'Cannot restore stale shares.{name} over existing values')
    for row in rows:
        bind.execute(
            sa.text(f'UPDATE shares SET {_q(row["field_name"])} = :value WHERE id = :share_id'),
            row,
        )


def _restore_stale_share_defaults(bind) -> None:
    if bind.dialect.name != 'sqlite':
        return
    defaults = bind.execute(sa.text(f"""
        SELECT DISTINCT source_column_default FROM {STALE_SHARE_AUDIT_TABLE}
        WHERE migration_revision = :revision AND field_name = 'hide_internal_fields'
    """), {'revision': revision}).scalars().all()
    if defaults == ['0']:
        with op.batch_alter_table('shares') as batch_op:
            batch_op.alter_column('hide_internal_fields', existing_type=sa.Boolean(), server_default=sa.text('0'))


def upgrade() -> None:
    bind = op.get_bind()
    evidence = _stale_share_value_plan(bind)
    _preflight(bind, evidence)
    _create_missing_tables(bind)
    _add_missing_columns(bind)
    _archive_stale_share_values(bind, evidence)
    _drop_null_only_stale_share_columns(bind)
    _postvalidate(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if STALE_SHARE_AUDIT_TABLE in _tables(bind):
        _validate_present_table(bind, STALE_SHARE_AUDIT_SPEC)
    rows = _stale_share_restore_rows(bind)
    _add_stale_share_columns_for_downgrade(bind)
    _restore_stale_share_values(bind, rows)
    _restore_stale_share_defaults(bind)
