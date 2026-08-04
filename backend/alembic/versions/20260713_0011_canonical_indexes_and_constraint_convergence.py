"""converge canonical indexes and named unique constraints

Revision ID: 20260713_0011
Revises: 20260713_0010
Create Date: 2026-07-13 22:00:00
"""

from __future__ import annotations

from alembic import op
import hashlib
import re
import sqlalchemy as sa


revision = '20260713_0011'
down_revision = '20260713_0010'
branch_labels = None
depends_on = None


IndexSpec = tuple[str, str, tuple[str, ...], bool, str | None]
EvidenceColumnSpec = tuple[str, str, bool, int, str]

# Later idempotent migrations may already have run when this historical
# convergence revision is replayed to repair a lost Alembic marker.
KNOWN_LATER_INDEXES: tuple[IndexSpec, ...] = (
    ('ix_horizons_projects_storage_root', 'horizons_projects', ('storage_root',), False, None),
    ('ix_transcodes_last_accessed', 'transcodes', ('last_accessed',), False, None),
    ('ix_upload_sessions_owner_user_id', 'upload_sessions', ('owner_user_id',), False, None),
)
KNOWN_LATER_INDEXES_BY_NAME = {item[0]: item for item in KNOWN_LATER_INDEXES}

CANONICAL_INDEXES: tuple[IndexSpec, ...] = (
    ('idx_activity_log_created', 'activity_log', ('created_at',), False, None),
    ('ix_agent_api_keys_key_prefix', 'agent_api_keys', ('key_prefix',), False, None),
    ('ix_agent_api_keys_secret_hash', 'agent_api_keys', ('secret_hash',), True, None),
    ('ix_agent_api_keys_user_id', 'agent_api_keys', ('user_id',), False, None),
    ('idx_agent_mutation_receipts_key', 'agent_mutation_receipts', ('agent_key_id',), False, None),
    ('idx_agent_mutation_receipts_op', 'agent_mutation_receipts', ('operation',), False, None),
    ('ix_agent_mutation_receipts_agent_key_id', 'agent_mutation_receipts', ('agent_key_id',), False, None),
    ('ix_agent_mutation_receipts_idempotency_key', 'agent_mutation_receipts', ('idempotency_key',), False, None),
    ('ix_agent_mutation_receipts_operation', 'agent_mutation_receipts', ('operation',), False, None),
    ('uq_agent_mutation_receipts_key_operation_idempotency', 'agent_mutation_receipts', ('agent_key_id', 'operation', 'idempotency_key'), True, None),
    ('idx_comments_project_id', 'comments', ('project_id',), False, None),
    ('idx_comments_project_asset_created', 'comments', ('project_id', 'horizons_media_asset_id', 'created_at'), False, None),
    ('idx_comments_project_file_created', 'comments', ('project_id', 'file_path', 'created_at'), False, None),
    ('idx_comments_project_version_created', 'comments', ('project_id', 'horizons_shot_version_id', 'created_at'), False, None),
    ('ix_comments_file_path', 'comments', ('file_path',), False, None),
    ('ix_comments_horizons_media_asset_id', 'comments', ('horizons_media_asset_id',), False, None),
    ('ix_comments_horizons_shot_version_id', 'comments', ('horizons_shot_version_id',), False, None),
    ('ix_comments_id', 'comments', ('id',), False, None),
    ('ix_comments_parent_comment_id', 'comments', ('parent_comment_id',), False, None),
    ('ix_comments_project_id', 'comments', ('project_id',), False, None),
    ('ix_comments_root_comment_id', 'comments', ('root_comment_id',), False, None),
    ('idx_download_events_project_created', 'download_events', ('project_id', 'created_at'), False, None),
    ('idx_download_events_project_tracker_created', 'download_events', ('project_id', 'tracker_id', 'created_at'), False, None),
    ('idx_download_events_share_created', 'download_events', ('share_id', 'created_at'), False, None),
    ('ix_download_events_created_at', 'download_events', ('created_at',), False, None),
    ('ix_download_events_event_type', 'download_events', ('event_type',), False, None),
    ('ix_download_events_ip_address', 'download_events', ('ip_address',), False, None),
    ('ix_download_events_project_id', 'download_events', ('project_id',), False, None),
    ('ix_download_events_resource_type', 'download_events', ('resource_type',), False, None),
    ('ix_download_events_share_id', 'download_events', ('share_id',), False, None),
    ('ix_download_events_source', 'download_events', ('source',), False, None),
    ('ix_download_events_tracker_id', 'download_events', ('tracker_id',), False, None),
    ('ix_download_events_user_id', 'download_events', ('user_id',), False, None),
    ('idx_file_operation_journal_operation_type', 'file_operation_journal', ('operation_type',), False, None),
    ('idx_file_operation_journal_project_id', 'file_operation_journal', ('project_id',), False, None),
    ('idx_file_operation_journal_status', 'file_operation_journal', ('status',), False, None),
    ('ix_file_operation_journal_operation_type', 'file_operation_journal', ('operation_type',), False, None),
    ('ix_file_operation_journal_project_id', 'file_operation_journal', ('project_id',), False, None),
    ('ix_file_operation_journal_status', 'file_operation_journal', ('status',), False, None),
    ('idx_horizons_pages_project_slug', 'horizons_pages', ('project_id', 'slug'), True, None),
    ('ix_horizons_pages_project_id', 'horizons_pages', ('project_id',), False, None),
    ('ix_horizons_pages_slug', 'horizons_pages', ('slug',), False, None),
    ('idx_horizons_grants_subject', 'horizons_project_grants', ('subject_type', 'subject_id'), False, None),
    ('idx_horizons_grants_unique', 'horizons_project_grants', ('project_id', 'subject_type', 'subject_id'), True, None),
    ('ix_horizons_project_grants_project_id', 'horizons_project_grants', ('project_id',), False, None),
    ('ix_horizons_project_grants_subject_id', 'horizons_project_grants', ('subject_id',), False, None),
    ('ix_horizons_projects_slug', 'horizons_projects', ('slug',), True, None),
    ('ix_horizons_shot_assignees_project_id', 'horizons_shot_assignees', ('project_id',), False, None),
    ('ix_horizons_shot_assignees_shot_id', 'horizons_shot_assignees', ('shot_id',), False, None),
    ('ix_horizons_shot_assignees_tracker_id', 'horizons_shot_assignees', ('tracker_id',), False, None),
    ('ix_horizons_shot_assignees_user_id', 'horizons_shot_assignees', ('user_id',), False, None),
    ('uq_horizon_shot_assignee_user', 'horizons_shot_assignees', ('shot_id', 'user_id'), True, None),
    ('idx_horizons_versions_project_media_created', 'horizons_shot_versions', ('project_id', 'media_asset_id', 'created_at'), False, None),
    ('idx_horizons_versions_project_shot_created', 'horizons_shot_versions', ('project_id', 'shot_id', 'created_at'), False, None),
    ('idx_horizons_versions_project_tracker_created', 'horizons_shot_versions', ('project_id', 'tracker_id', 'created_at'), False, None),
    ('idx_horizons_versions_shot_label', 'horizons_shot_versions', ('shot_id', 'label'), True, None),
    ('ix_horizons_shot_versions_media_asset_id', 'horizons_shot_versions', ('media_asset_id',), False, None),
    ('ix_horizons_shot_versions_project_id', 'horizons_shot_versions', ('project_id',), False, None),
    ('ix_horizons_shot_versions_shot_id', 'horizons_shot_versions', ('shot_id',), False, None),
    ('ix_horizons_shot_versions_tracker_id', 'horizons_shot_versions', ('tracker_id',), False, None),
    ('idx_horizons_shots_project_status_created', 'horizons_shots', ('project_id', 'status', 'created_at'), False, None),
    ('idx_horizons_shots_project_tracker_archived', 'horizons_shots', ('project_id', 'tracker_id', 'archived_at'), False, None),
    ('idx_horizons_shots_project_tracker_created', 'horizons_shots', ('project_id', 'tracker_id', 'created_at'), False, None),
    ('idx_horizons_shots_project_tracker_status', 'horizons_shots', ('project_id', 'tracker_id', 'status'), False, None),
    ('idx_horizons_shots_tracker_code', 'horizons_shots', ('tracker_id', 'shot_code'), True, None),
    ('ix_horizons_shots_archived_at', 'horizons_shots', ('archived_at',), False, None),
    ('ix_horizons_shots_assignee_user_id', 'horizons_shots', ('assignee_user_id',), False, None),
    ('ix_horizons_shots_latest_media_asset_id', 'horizons_shots', ('latest_media_asset_id',), False, None),
    ('ix_horizons_shots_project_id', 'horizons_shots', ('project_id',), False, None),
    ('ix_horizons_shots_shot_code', 'horizons_shots', ('shot_code',), False, None),
    ('ix_horizons_shots_tracker_id', 'horizons_shots', ('tracker_id',), False, None),
    ('idx_horizons_trackers_project_created', 'horizons_trackers', ('project_id', 'created_at'), False, None),
    ('idx_horizons_trackers_project_slug', 'horizons_trackers', ('project_id', 'slug'), True, None),
    ('ix_horizons_trackers_project_id', 'horizons_trackers', ('project_id',), False, None),
    ('ix_horizons_trackers_slug', 'horizons_trackers', ('slug',), False, None),
    ('idx_media_assets_project_hash', 'media_assets', ('project_id', 'content_hash'), False, None),
    ('idx_media_assets_project_scope_path', 'media_assets', ('project_id', 'storage_scope', 'file_path'), False, None),
    ('idx_media_assets_project_scope_path_available', 'media_assets', ('project_id', 'storage_scope', 'file_path', 'unavailable_at'), False, None),
    ('idx_media_assets_source_signature', 'media_assets', ('source_signature',), False, None),
    ('idx_media_assets_unavailable_at', 'media_assets', ('unavailable_at',), False, None),
    ('ix_media_assets_project_id', 'media_assets', ('project_id',), False, None),
    ('ix_media_assets_source_signature', 'media_assets', ('source_signature',), False, None),
    ('ix_media_assets_unavailable_at', 'media_assets', ('unavailable_at',), False, None),
    ('uq_media_assets_active_owner_scope_path', 'media_assets', ('project_id', 'storage_scope', 'file_path'), True, 'unavailable_at IS NULL'),
    ('ix_media_metadata_media_asset_id', 'media_metadata', ('media_asset_id',), False, None),
    ('ix_notification_deliveries_next_attempt_at', 'notification_deliveries', ('next_attempt_at',), False, None),
    ('ix_notification_deliveries_provider', 'notification_deliveries', ('provider',), False, None),
    ('ix_notification_deliveries_recipient_user_id', 'notification_deliveries', ('recipient_user_id',), False, None),
    ('ix_notification_deliveries_status', 'notification_deliveries', ('status',), False, None),
    ('ix_notification_deliveries_subscription_id', 'notification_deliveries', ('subscription_id',), False, None),
    ('ix_notification_deliveries_tracker_event_id', 'notification_deliveries', ('tracker_event_id',), False, None),
    ('uq_notification_delivery_event_subscription_recipient', 'notification_deliveries', ('tracker_event_id', 'subscription_id', 'recipient_user_id'), True, None),
    ('ix_notification_read_state_user_id', 'notification_read_state', ('user_id',), False, None),
    ('uq_notification_read_state_user_feed', 'notification_read_state', ('user_id', 'feed_key'), True, None),
    ('ix_notification_subscriptions_provider', 'notification_subscriptions', ('provider',), False, None),
    ('ix_notification_subscriptions_recipient_user_id', 'notification_subscriptions', ('recipient_user_id',), False, None),
    ('idx_recently_viewed_time', 'recently_viewed', ('viewed_at',), False, None),
    ('idx_recently_viewed_user', 'recently_viewed', ('user_id',), False, None),
    ('ix_recently_viewed_user_id', 'recently_viewed', ('user_id',), False, None),
    ('idx_shares_media_asset_id', 'shares', ('media_asset_id',), False, None),
    ('idx_shares_project_created', 'shares', ('project_id', 'created_at'), False, None),
    ('idx_shares_project_id', 'shares', ('project_id',), False, None),
    ('idx_shares_project_tracker', 'shares', ('project_id', 'tracker_id'), False, None),
    ('idx_shares_share_id', 'shares', ('id',), False, None),
    ('ix_shares_media_asset_id', 'shares', ('media_asset_id',), False, None),
    ('idx_shot_registry_project', 'shot_registry', ('project_id',), False, None),
    ('idx_shot_registry_project_tracker_id', 'shot_registry', ('project_id', 'tracker_id'), False, None),
    ('idx_shot_registry_shot', 'shot_registry', ('project_id', 'shot_id'), False, None),
    ('idx_shot_registry_tracker', 'shot_registry', ('project_id', 'tracker_name'), False, None),
    ('ix_shot_registry_latest_media_asset_id', 'shot_registry', ('latest_media_asset_id',), False, None),
    ('ix_shot_registry_project_id', 'shot_registry', ('project_id',), False, None),
    ('ix_shot_registry_shot_id', 'shot_registry', ('shot_id',), False, None),
    ('ix_shot_registry_tracker_id', 'shot_registry', ('tracker_id',), False, None),
    ('ix_shot_registry_tracker_name', 'shot_registry', ('tracker_name',), False, None),
    ('idx_tracker_events_project_tracker_created', 'tracker_events', ('project_id', 'tracker_id', 'created_at'), False, None),
    ('ix_tracker_events_comment_id', 'tracker_events', ('comment_id',), False, None),
    ('ix_tracker_events_created_at', 'tracker_events', ('created_at',), False, None),
    ('ix_tracker_events_event_type', 'tracker_events', ('event_type',), False, None),
    ('ix_tracker_events_project_id', 'tracker_events', ('project_id',), False, None),
    ('ix_tracker_events_shot_id', 'tracker_events', ('shot_id',), False, None),
    ('ix_tracker_events_shot_version_id', 'tracker_events', ('shot_version_id',), False, None),
    ('ix_tracker_events_tracker_id', 'tracker_events', ('tracker_id',), False, None),
    ('ix_transcodes_file_path', 'transcodes', ('file_path',), True, None),
    ('ix_upload_items_completed_at', 'upload_items', ('completed_at',), False, None),
    ('ix_upload_items_final_path', 'upload_items', ('final_path',), False, None),
    ('ix_upload_items_session_id', 'upload_items', ('session_id',), False, None),
    ('ix_upload_sessions_client_batch_id', 'upload_sessions', ('client_batch_id',), False, None),
    ('ix_upload_sessions_expires_at', 'upload_sessions', ('expires_at',), False, None),
    ('ix_upload_sessions_project_id', 'upload_sessions', ('project_id',), False, None),
    ('ix_upload_sessions_scope_type', 'upload_sessions', ('scope_type',), False, None),
    ('ix_upload_sessions_share_id', 'upload_sessions', ('share_id',), False, None),
    ('ix_user_preferences_user_id', 'user_preferences', ('user_id',), True, None),
    ('ix_user_sessions_expires_at', 'user_sessions', ('expires_at',), False, None),
    ('ix_user_sessions_user_id', 'user_sessions', ('user_id',), False, None),
    ('idx_version_registry_project', 'version_registry', ('project_id',), False, None),
    ('idx_version_registry_project_tracker_id', 'version_registry', ('project_id', 'tracker_id'), False, None),
    ('idx_version_registry_shot', 'version_registry', ('project_id', 'shot_id'), False, None),
    ('idx_version_registry_tracker', 'version_registry', ('project_id', 'tracker_name'), False, None),
    ('ix_version_registry_media_asset_id', 'version_registry', ('media_asset_id',), False, None),
    ('ix_version_registry_project_id', 'version_registry', ('project_id',), False, None),
    ('ix_version_registry_shot_id', 'version_registry', ('shot_id',), False, None),
    ('ix_version_registry_tracker_name', 'version_registry', ('tracker_name',), False, None),
    ('ix_version_registry_variant_id', 'version_registry', ('variant_id',), False, None),
)

TOLERATED_ALIASES: tuple[IndexSpec, ...] = (
    ('idx_agent_api_keys_prefix', 'agent_api_keys', ('key_prefix',), False, None),
    ('idx_agent_api_keys_user', 'agent_api_keys', ('user_id',), False, None),
    ('idx_comments_horizons_media_asset_id', 'comments', ('horizons_media_asset_id',), False, None),
    ('idx_comments_horizons_shot_version_id', 'comments', ('horizons_shot_version_id',), False, None),
    ('idx_comments_parent_comment_id', 'comments', ('parent_comment_id',), False, None),
    ('idx_comments_root_comment_id', 'comments', ('root_comment_id',), False, None),
    ('idx_download_events_created', 'download_events', ('created_at',), False, None),
    ('idx_download_events_ip', 'download_events', ('ip_address',), False, None),
    ('idx_download_events_project', 'download_events', ('project_id',), False, None),
    ('idx_download_events_share', 'download_events', ('share_id',), False, None),
    ('idx_download_events_type', 'download_events', ('event_type',), False, None),
    ('idx_download_events_user', 'download_events', ('user_id',), False, None),
    ('idx_horizon_shot_assignees_project', 'horizons_shot_assignees', ('project_id',), False, None),
    ('idx_horizon_shot_assignees_shot', 'horizons_shot_assignees', ('shot_id',), False, None),
    ('idx_horizon_shot_assignees_tracker', 'horizons_shot_assignees', ('tracker_id',), False, None),
    ('idx_horizon_shot_assignees_user', 'horizons_shot_assignees', ('user_id',), False, None),
    ('idx_horizons_grants_project', 'horizons_project_grants', ('project_id',), False, None),
    ('idx_horizons_pages_project', 'horizons_pages', ('project_id',), False, None),
    ('idx_horizons_projects_slug', 'horizons_projects', ('slug',), True, None),
    ('idx_horizons_shots_project', 'horizons_shots', ('project_id',), False, None),
    ('idx_horizons_shots_tracker', 'horizons_shots', ('tracker_id',), False, None),
    ('idx_horizons_trackers_project', 'horizons_trackers', ('project_id',), False, None),
    ('idx_horizons_versions_project', 'horizons_shot_versions', ('project_id',), False, None),
    ('idx_horizons_versions_shot', 'horizons_shot_versions', ('shot_id',), False, None),
    ('idx_horizons_versions_tracker', 'horizons_shot_versions', ('tracker_id',), False, None),
    ('idx_media_assets_project', 'media_assets', ('project_id',), False, None),
    ('idx_media_metadata_asset', 'media_metadata', ('media_asset_id',), False, None),
    ('idx_notification_deliveries_event', 'notification_deliveries', ('tracker_event_id',), False, None),
    ('idx_notification_deliveries_next_attempt', 'notification_deliveries', ('next_attempt_at',), False, None),
    ('idx_notification_deliveries_provider', 'notification_deliveries', ('provider',), False, None),
    ('idx_notification_deliveries_recipient', 'notification_deliveries', ('recipient_user_id',), False, None),
    ('idx_notification_deliveries_status', 'notification_deliveries', ('status',), False, None),
    ('idx_notification_deliveries_subscription', 'notification_deliveries', ('subscription_id',), False, None),
    ('idx_notification_deliveries_unique', 'notification_deliveries', ('tracker_event_id', 'subscription_id', 'recipient_user_id'), True, None),
    ('idx_notification_read_state_unique', 'notification_read_state', ('user_id', 'feed_key'), True, None),
    ('idx_notification_read_state_user', 'notification_read_state', ('user_id',), False, None),
    ('idx_notification_subscriptions_provider', 'notification_subscriptions', ('provider',), False, None),
    ('idx_notification_subscriptions_recipient', 'notification_subscriptions', ('recipient_user_id',), False, None),
    ('idx_tracker_events_created', 'tracker_events', ('created_at',), False, None),
    ('idx_tracker_events_shot', 'tracker_events', ('shot_id',), False, None),
    ('idx_tracker_events_version', 'tracker_events', ('shot_version_id',), False, None),
    ('idx_upload_items_completed', 'upload_items', ('completed_at',), False, None),
    ('idx_upload_items_final_path', 'upload_items', ('final_path',), False, None),
    ('idx_upload_items_session', 'upload_items', ('session_id',), False, None),
    ('idx_upload_sessions_batch', 'upload_sessions', ('client_batch_id',), False, None),
    ('idx_upload_sessions_expires', 'upload_sessions', ('expires_at',), False, None),
    ('idx_upload_sessions_project', 'upload_sessions', ('project_id',), False, None),
    ('idx_upload_sessions_scope', 'upload_sessions', ('scope_type',), False, None),
    ('idx_upload_sessions_share', 'upload_sessions', ('share_id',), False, None),
    ('idx_user_sessions_expires', 'user_sessions', ('expires_at',), False, None),
    ('idx_user_sessions_user', 'user_sessions', ('user_id',), False, None),
)

RETIRED_INDEXES: tuple[IndexSpec, ...] = (
    ('idx_agent_mutation_receipts_unique', 'agent_mutation_receipts', ('agent_key_id', 'operation', 'idempotency_key'), True, None),
    ('idx_media_assets_project_path', 'media_assets', ('project_id', 'file_path'), False, None),
    ('idx_tracker_events_project_tracker', 'tracker_events', ('project_id', 'tracker_id'), False, None),
    ('idx_user_prefs_user', 'user_preferences', ('user_id',), False, None),
    ('user_preferences_user_id_key', 'user_preferences', ('user_id',), True, None),
)

MANIFEST_BY_NAME = {item[0]: item for item in CANONICAL_INDEXES + TOLERATED_ALIASES + RETIRED_INDEXES}
CANONICAL_BY_NAME = {item[0]: item for item in CANONICAL_INDEXES}
RETIRED_BY_NAME = {item[0]: item for item in RETIRED_INDEXES}
MANIFEST_TABLES = {item[1] for item in CANONICAL_INDEXES + TOLERATED_ALIASES + RETIRED_INDEXES}
UNIQUE_MANIFEST_BY_TABLE = {}
for _spec in CANONICAL_INDEXES + TOLERATED_ALIASES + RETIRED_INDEXES:
    if _spec[3]:
        UNIQUE_MANIFEST_BY_TABLE.setdefault(_spec[1], set()).add(_spec[2])

INDEX_EVIDENCE_TABLE = 'alembic_0011_index_ownership'
RECEIPT_AUDIT_TABLE = 'alembic_0011_receipt_dedupe_audit'
SENTINEL_ACTION = 'execution_complete'
SENTINEL_OBJECT = '__0011_index_ownership_complete__'
SENTINEL_DIGEST_PREFIX = 'sha256:'
INDEX_EVIDENCE_SCHEMA: tuple[EvidenceColumnSpec, ...] = (
    ('id', 'integer', False, 1, 'pk_identity'),
    ('migration_revision', 'string', False, 0, 'none'),
    ('action', 'string', False, 0, 'none'),
    ('object_name', 'string', False, 0, 'none'),
    ('table_name', 'string', False, 0, 'none'),
    ('columns_csv', 'text', False, 0, 'none'),
    ('is_unique', 'integer', False, 0, 'none'),
    ('predicate', 'text', True, 0, 'none'),
    ('dialect', 'string', False, 0, 'none'),
)
RECEIPT_AUDIT_SCHEMA: tuple[EvidenceColumnSpec, ...] = (
    ('audit_id', 'integer', False, 1, 'pk_identity'),
    ('migration_revision', 'string', False, 0, 'none'),
    ('canonical_receipt_id', 'string', False, 0, 'none'),
    ('id', 'string', False, 0, 'none'),
    ('agent_key_id', 'string', False, 0, 'none'),
    ('operation', 'string', False, 0, 'none'),
    ('idempotency_key', 'string', False, 0, 'none'),
    ('response_json', 'text', False, 0, 'none'),
    ('created_at', 'float', True, 0, 'none'),
)


def _ident(value: str) -> str:
    if not value.replace('_', '').isalnum():
        raise ValueError(f'Unsafe SQL identifier: {value!r}')
    return value


def _q(value: str) -> str:
    return f'"{_ident(value)}"'


def _normalize_predicate(predicate: str | None) -> str | None:
    if predicate is None:
        return None
    text = predicate.strip().rstrip(';').lower().replace('"', '').replace('(', '').replace(')', '')
    text = ' '.join(text.split())
    return text


def _columns_csv(columns: tuple[str, ...]) -> str:
    return ','.join(columns)


def _type_family(column_type) -> str:
    if isinstance(column_type, sa.Text):
        return 'text'
    if isinstance(column_type, sa.Integer):
        return 'integer'
    if isinstance(column_type, sa.Float):
        return 'float'
    if isinstance(column_type, sa.String):
        return 'string'
    return type(column_type).__name__.lower()


def _has_expected_default(column, default_rule: str) -> bool:
    default = column.get('default')
    if default_rule == 'none':
        return default is None
    if default_rule == 'pk_identity':
        return default is None or 'nextval(' in str(default).lower()
    raise RuntimeError(f'0011 has unknown evidence default rule {default_rule}')


def _table_columns(bind, table_name: str) -> set[str]:
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def _sqlite_index_columns(bind, name: str) -> tuple[str, ...]:
    return tuple(
        item['name']
        for item in bind.execute(sa.text(f'PRAGMA index_info({_q(name)})')).mappings().all()
    )


def _sqlite_predicate(sql: str | None) -> str | None:
    if not sql:
        return None
    match = list(re.finditer(r'\bwhere\b', sql, flags=re.IGNORECASE))
    if not match:
        return None
    return sql[match[-1].end():].strip()


def _validate_sqlite_generated_index(bind, table_name: str, row) -> None:
    name = row['name']
    columns = _sqlite_index_columns(bind, name)
    origin = row['origin']
    if origin == 'pk':
        pk_columns = tuple(sa.inspect(bind).get_pk_constraint(table_name).get('constrained_columns') or ())
        if columns != pk_columns or not row['unique']:
            raise RuntimeError(f'0011 rejects incompatible SQLite generated primary key {table_name}.{name}')
        return
    if origin == 'u':
        if columns not in UNIQUE_MANIFEST_BY_TABLE.get(table_name, set()) or not row['unique']:
            raise RuntimeError(f'0011 rejects incompatible SQLite generated unique index {table_name}.{name}')
        return
    raise RuntimeError(f'0011 rejects unsupported SQLite generated index {table_name}.{name}')


def _sqlite_indexes(bind, table_name: str) -> dict[str, tuple[tuple[str, ...], bool, str | None]]:
    rows = bind.execute(sa.text(f'PRAGMA index_list({_q(table_name)})')).mappings().all()
    result = {}
    for row in rows:
        name = row['name']
        if name.startswith('sqlite_autoindex_'):
            _validate_sqlite_generated_index(bind, table_name, row)
            continue
        columns = _sqlite_index_columns(bind, name)
        sql = bind.execute(
            sa.text('SELECT sql FROM sqlite_master WHERE type = "index" AND name = :name'),
            {'name': name},
        ).scalar()
        predicate = _sqlite_predicate(sql)
        result[name] = (columns, bool(row['unique']), _normalize_predicate(predicate))
    return result


def _postgres_constraint(bind, table_name: str, index_name: str):
    return bind.execute(sa.text("""
        SELECT con.conname, con.contype,
               array_agg(att.attname ORDER BY key.ord) AS columns
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN unnest(con.conkey) WITH ORDINALITY AS key(attnum, ord) ON true
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = key.attnum
        WHERE nsp.nspname = current_schema()
          AND rel.relname = :table_name
          AND con.conname = :index_name
        GROUP BY con.conname, con.contype
    """), {'table_name': table_name, 'index_name': index_name}).mappings().first()


def _validate_postgres_generated_index(bind, table_name: str, name: str, columns: tuple[str, ...], unique: bool) -> bool:
    constraint = _postgres_constraint(bind, table_name, name)
    if constraint is None:
        return False
    constraint_columns = tuple(constraint['columns'])
    if constraint['contype'] == 'p':
        expected_name = 'alembic_version_pkc' if table_name == 'alembic_version' else f'{table_name}_pkey'
        if name != expected_name:
            raise RuntimeError(f'0011 rejects renamed PostgreSQL primary key {table_name}.{name}')
        if columns != constraint_columns or not unique:
            raise RuntimeError(f'0011 rejects incompatible PostgreSQL primary key {table_name}.{name}')
        return True
    if name in MANIFEST_BY_NAME:
        return False
    raise RuntimeError(f'0011 rejects unsupported PostgreSQL constraint index {table_name}.{name}')


def _postgres_indexes(bind, table_name: str) -> dict[str, tuple[tuple[str, ...], bool, str | None]]:
    rows = bind.execute(sa.text("""
        SELECT
          c.relname AS name,
          indisunique AS is_unique,
          pg_get_indexdef(i.indexrelid) AS indexdef,
          pg_get_expr(i.indpred, i.indrelid) AS predicate
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = current_schema() AND t.relname = :table_name
    """), {'table_name': table_name}).mappings().all()
    result = {}
    for row in rows:
        name = row['name']
        inside = row['indexdef'].split('(', 1)[1].split(')', 1)[0]
        columns = tuple(part.strip().strip('"') for part in inside.split(','))
        if _validate_postgres_generated_index(bind, table_name, name, columns, bool(row['is_unique'])):
            continue
        result[name] = (columns, bool(row['is_unique']), _normalize_predicate(row['predicate']))
    return result


def _indexes(bind, table_name: str) -> dict[str, tuple[tuple[str, ...], bool, str | None]]:
    if bind.dialect.name == 'sqlite':
        return _sqlite_indexes(bind, table_name)
    return _postgres_indexes(bind, table_name)


def _matches(actual: tuple[tuple[str, ...], bool, str | None], spec: IndexSpec) -> bool:
    _name, _table, columns, unique, predicate = spec
    return actual == (tuple(columns), unique, _normalize_predicate(predicate))


def _preflight_indexes(bind) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    for table_name in MANIFEST_TABLES:
        if table_name not in tables:
            raise RuntimeError(f'0011 cannot inspect missing manifest table {table_name}')
        columns = _table_columns(bind, table_name)
        for name, _table, wanted_columns, _unique, _predicate in (
            item for item in CANONICAL_INDEXES if item[1] == table_name
        ):
            missing = set(wanted_columns) - columns
            if missing:
                raise RuntimeError(f'0011 cannot create {name}: missing columns {sorted(missing)!r}')
        for name, actual in _indexes(bind, table_name).items():
            spec = MANIFEST_BY_NAME.get(name)
            if spec is None:
                later_spec = KNOWN_LATER_INDEXES_BY_NAME.get(name)
                if later_spec is not None and later_spec[1] == table_name and _matches(actual, later_spec):
                    continue
                raise RuntimeError(f'0011 rejects unknown index {table_name}.{name}')
            if not _matches(actual, spec):
                raise RuntimeError(f'0011 rejects incompatible index {table_name}.{name}')


def _preflight_evidence_tables(bind) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    expected = {
        INDEX_EVIDENCE_TABLE: INDEX_EVIDENCE_SCHEMA,
        RECEIPT_AUDIT_TABLE: RECEIPT_AUDIT_SCHEMA,
    }
    for table_name, schema in expected.items():
        if table_name not in tables:
            continue
        actual = sa.inspect(bind).get_columns(table_name)
        if len(actual) != len(schema):
            raise RuntimeError(f'0011 rejects incompatible migration evidence table {table_name}')
        pk_columns = sa.inspect(bind).get_pk_constraint(table_name).get('constrained_columns') or ()
        pk_order_by_name = {name: index for index, name in enumerate(pk_columns, start=1)}
        for column, wanted in zip(actual, schema, strict=True):
            name, family, nullable, pk_order, default_rule = wanted
            if column['name'] != name:
                raise RuntimeError(f'0011 rejects incompatible migration evidence table {table_name}')
            if _type_family(column['type']) != family:
                raise RuntimeError(f'0011 rejects incompatible migration evidence table {table_name}')
            if bool(column['nullable']) != nullable:
                raise RuntimeError(f'0011 rejects incompatible migration evidence table {table_name}')
            actual_pk_order = int(column.get('primary_key') or pk_order_by_name.get(name, 0) or 0)
            if actual_pk_order != pk_order:
                raise RuntimeError(f'0011 rejects incompatible migration evidence table {table_name}')
            if not _has_expected_default(column, default_rule):
                raise RuntimeError(f'0011 rejects incompatible migration evidence table {table_name}')


def _preflight_empty_ownership_table(bind) -> None:
    if INDEX_EVIDENCE_TABLE not in set(sa.inspect(bind).get_table_names()):
        return
    count = bind.execute(sa.text(f'SELECT COUNT(*) FROM {_q(INDEX_EVIDENCE_TABLE)}')).scalar()
    if count:
        raise RuntimeError('0011 rejects preexisting index ownership evidence rows')


def _ownership_spec_for_row(row) -> IndexSpec:
    action = row['action']
    if action == 'created_canonical':
        expected = CANONICAL_BY_NAME.get(row['object_name'])
    elif action == 'removed_retired':
        expected = RETIRED_BY_NAME.get(row['object_name'])
    else:
        expected = None
    if expected is None:
        raise RuntimeError('0011 rejects malformed index ownership evidence row')
    name, table_name, columns, unique, predicate = expected
    if row['table_name'] != table_name:
        raise RuntimeError('0011 rejects malformed index ownership evidence row')
    if row['columns_csv'] != _columns_csv(columns):
        raise RuntimeError('0011 rejects malformed index ownership evidence row')
    if row['is_unique'] not in (0, 1, False, True) or bool(row['is_unique']) != unique:
        raise RuntimeError('0011 rejects malformed index ownership evidence row')
    if _normalize_predicate(row['predicate']) != _normalize_predicate(predicate):
        raise RuntimeError('0011 rejects malformed index ownership evidence row')
    return name, table_name, columns, unique, predicate


def _ownership_digest(rows) -> str:
    digest = hashlib.sha256()
    fields = ('migration_revision', 'action', 'object_name', 'table_name', 'columns_csv', 'is_unique', 'predicate', 'dialect')
    for row in sorted(rows, key=lambda item: tuple(str(int(item[field])) if field == 'is_unique' else (item[field] or '') for field in fields)):
        for field in (
            'migration_revision', 'action', 'object_name', 'table_name',
            'columns_csv', 'is_unique', 'predicate', 'dialect',
        ):
            value = str(int(row[field])) if field == 'is_unique' else (row[field] or '')
            encoded = value.encode()
            digest.update(str(len(encoded)).encode() + b':' + encoded)
    return SENTINEL_DIGEST_PREFIX + digest.hexdigest()


def _record_completion_sentinel(bind) -> None:
    rows = bind.execute(sa.text(f"""
        SELECT migration_revision, action, object_name, table_name,
               columns_csv, is_unique, predicate, dialect
        FROM {_q(INDEX_EVIDENCE_TABLE)} WHERE migration_revision = :revision AND action != :sentinel_action
    """), {'revision': revision, 'sentinel_action': SENTINEL_ACTION}).mappings().all()
    bind.execute(sa.text(f"""
        INSERT INTO {_q(INDEX_EVIDENCE_TABLE)} (
            migration_revision, action, object_name, table_name,
            columns_csv, is_unique, predicate, dialect
        ) VALUES (
            :revision, :action, :object_name, :table_name,
            :count, 0, :digest, :dialect
        )
    """), {
        'revision': revision,
        'action': SENTINEL_ACTION,
        'object_name': SENTINEL_OBJECT,
        'table_name': INDEX_EVIDENCE_TABLE,
        'count': str(len(rows)),
        'digest': _ownership_digest(rows),
        'dialect': bind.dialect.name,
    })


def _validated_current_ownership_rows(bind):
    if INDEX_EVIDENCE_TABLE not in set(sa.inspect(bind).get_table_names()):
        raise RuntimeError('0011 downgrade requires index ownership evidence')
    rows = bind.execute(sa.text(f"""
        SELECT id, migration_revision, action, object_name, table_name,
               columns_csv, is_unique, predicate, dialect
        FROM {_q(INDEX_EVIDENCE_TABLE)}
        ORDER BY id
    """)).mappings().all()
    if not rows:
        raise RuntimeError('0011 downgrade requires current index ownership evidence')
    if any(row['migration_revision'] != revision for row in rows):
        raise RuntimeError('0011 rejects wrong-revision index ownership evidence row')
    if any(row['dialect'] != bind.dialect.name for row in rows):
        raise RuntimeError('0011 rejects wrong-dialect index ownership evidence row')
    sentinels = [row for row in rows if row['action'] == SENTINEL_ACTION]
    if len(sentinels) != 1:
        raise RuntimeError('0011 downgrade requires exactly one index ownership completion sentinel')
    sentinel = sentinels[0]
    non_sentinel = [row for row in rows if row['action'] != SENTINEL_ACTION]
    if (
        sentinel['object_name'] != SENTINEL_OBJECT
        or sentinel['table_name'] != INDEX_EVIDENCE_TABLE
        or sentinel['is_unique'] not in (0, False)
    ):
        raise RuntimeError('0011 rejects malformed index ownership completion sentinel')
    seen_actions = set()
    seen_names = set()
    validated = []
    for row in non_sentinel:
        key = (row['action'], row['object_name'])
        if key in seen_actions or row['object_name'] in seen_names:
            raise RuntimeError('0011 rejects duplicate index ownership evidence row')
        seen_actions.add(key)
        seen_names.add(row['object_name'])
        validated.append((row, _ownership_spec_for_row(row)))
    if sentinel['columns_csv'] != str(len(non_sentinel)) or sentinel['predicate'] != _ownership_digest(non_sentinel):
        raise RuntimeError('0011 rejects malformed index ownership completion sentinel')
    return validated


def _preflight_downgrade_objects(bind, rows) -> None:
    _preflight_indexes(bind)
    indexes_by_table = {table_name: _indexes(bind, table_name) for table_name in MANIFEST_TABLES}
    for row, spec in rows:
        actual = indexes_by_table[spec[1]].get(spec[0])
        if row['action'] == 'created_canonical':
            if actual is None or not _matches(actual, spec):
                raise RuntimeError(f'0011 downgrade rejects incompatible owned index {spec[1]}.{spec[0]}')
        elif actual is not None:
            raise RuntimeError(f'0011 downgrade rejects present retired index {spec[1]}.{spec[0]}')


def _preflight_receipts(bind) -> None:
    if 'agent_mutation_receipts' not in MANIFEST_TABLES:
        return
    if bind.dialect.name == 'sqlite':
        response_expr = "COUNT(DISTINCT typeof(response_json) || COALESCE(hex(CAST(response_json AS BLOB)), ''))"
        timestamp_expr = "COUNT(DISTINCT typeof(created_at) || COALESCE(hex(CAST(created_at AS BLOB)), ''))"
    else:
        response_expr = "COUNT(DISTINCT response_json) + CASE WHEN COUNT(response_json) = COUNT(*) THEN 0 ELSE 1000000 END"
        timestamp_expr = "CASE WHEN COUNT(created_at) = 0 THEN 1 WHEN COUNT(created_at) = COUNT(*) AND MIN(created_at) = MAX(created_at) THEN 1 ELSE 2 END"
    rows = bind.execute(sa.text(f"""
        SELECT {response_expr} AS responses, {timestamp_expr} AS timestamps
        FROM agent_mutation_receipts
        GROUP BY agent_key_id, operation, idempotency_key
        HAVING COUNT(*) > 1
    """)).mappings().all()
    if any(row['responses'] != 1 or row['timestamps'] != 1 for row in rows):
        raise RuntimeError('0011 refuses non-identical duplicate agent mutation receipts')


def _preflight_active_media(bind) -> None:
    rows = bind.execute(sa.text("""
        SELECT project_id, storage_scope, file_path, COUNT(*) AS n
        FROM media_assets
        WHERE unavailable_at IS NULL
        GROUP BY project_id, storage_scope, file_path
        HAVING COUNT(*) > 1
    """)).mappings().all()
    if rows:
        raise RuntimeError('0011 refuses duplicate active media asset bindings')


def _dedupe_receipts(bind) -> None:
    bind.execute(sa.text(f"""
        INSERT INTO {_q(RECEIPT_AUDIT_TABLE)} (
            migration_revision, canonical_receipt_id, id, agent_key_id, operation,
            idempotency_key, response_json, created_at
        )
        SELECT :revision, kept.keep_id, receipt.id, receipt.agent_key_id, receipt.operation,
               receipt.idempotency_key, receipt.response_json, receipt.created_at
        FROM agent_mutation_receipts AS receipt
        JOIN (
            SELECT agent_key_id, operation, idempotency_key, MIN(id) AS keep_id, COUNT(*) AS n
            FROM agent_mutation_receipts
            GROUP BY agent_key_id, operation, idempotency_key
            HAVING COUNT(*) > 1
        ) AS kept
          ON kept.agent_key_id = receipt.agent_key_id
         AND kept.operation = receipt.operation
         AND kept.idempotency_key = receipt.idempotency_key
        WHERE receipt.id != kept.keep_id
    """), {'revision': revision})
    bind.execute(sa.text("""
        DELETE FROM agent_mutation_receipts
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM agent_mutation_receipts
            GROUP BY agent_key_id, operation, idempotency_key
        )
    """))


def _create_index(bind, spec: IndexSpec) -> None:
    name, table_name, columns, unique, predicate = spec
    prefix = 'CREATE UNIQUE INDEX' if unique else 'CREATE INDEX'
    sql = f'{prefix} IF NOT EXISTS {_q(name)} ON {_q(table_name)} ({", ".join(_q(c) for c in columns)})'
    if predicate:
        sql += f' WHERE {predicate}'
    bind.execute(sa.text(sql))


def _create_evidence_tables() -> None:
    bind = op.get_bind()
    if INDEX_EVIDENCE_TABLE not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            INDEX_EVIDENCE_TABLE,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('migration_revision', sa.String(), nullable=False),
            sa.Column('action', sa.String(), nullable=False),
            sa.Column('object_name', sa.String(), nullable=False),
            sa.Column('table_name', sa.String(), nullable=False),
            sa.Column('columns_csv', sa.Text(), nullable=False),
            sa.Column('is_unique', sa.Integer(), nullable=False),
            sa.Column('predicate', sa.Text(), nullable=True),
            sa.Column('dialect', sa.String(), nullable=False),
        )
    if RECEIPT_AUDIT_TABLE not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            RECEIPT_AUDIT_TABLE,
            sa.Column('audit_id', sa.Integer(), primary_key=True),
            sa.Column('migration_revision', sa.String(), nullable=False),
            sa.Column('canonical_receipt_id', sa.String(), nullable=False),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('agent_key_id', sa.String(), nullable=False),
            sa.Column('operation', sa.String(), nullable=False),
            sa.Column('idempotency_key', sa.String(), nullable=False),
            sa.Column('response_json', sa.Text(), nullable=False),
            sa.Column('created_at', sa.Float(), nullable=True),
        )


def _record_index_evidence(bind, action: str, spec: IndexSpec) -> None:
    name, table_name, columns, unique, predicate = spec
    bind.execute(sa.text(f"""
        INSERT INTO {_q(INDEX_EVIDENCE_TABLE)} (
            migration_revision, action, object_name, table_name,
            columns_csv, is_unique, predicate, dialect
        ) VALUES (
            :revision, :action, :object_name, :table_name,
            :columns_csv, :is_unique, :predicate, :dialect
        )
    """), {
        'revision': revision,
        'action': action,
        'object_name': name,
        'table_name': table_name,
        'columns_csv': _columns_csv(columns),
        'is_unique': 1 if unique else 0,
        'predicate': predicate,
        'dialect': bind.dialect.name,
    })


def _drop_index(bind, name: str, table_name: str | None = None) -> None:
    if bind.dialect.name == 'postgresql' and table_name is not None:
        if _postgres_constraint(bind, table_name, name) is not None:
            bind.execute(sa.text(f'ALTER TABLE {_q(table_name)} DROP CONSTRAINT IF EXISTS {_q(name)}'))
            return
    bind.execute(sa.text(f'DROP INDEX IF EXISTS {_q(name)}'))


def _create_missing_canonical_indexes(bind) -> None:
    for spec in CANONICAL_INDEXES:
        name, table_name, _columns, _unique, _predicate = spec
        if name in _indexes(bind, table_name):
            continue
        _create_index(bind, spec)
        _record_index_evidence(bind, 'created_canonical', spec)


def _retire_replaced_indexes(bind) -> None:
    for spec in RETIRED_INDEXES:
        name, table_name, _columns, _unique, _predicate = spec
        if name in _indexes(bind, table_name):
            _record_index_evidence(bind, 'removed_retired', spec)
            _drop_index(bind, name, table_name)


def _postvalidate(bind) -> None:
    for spec in CANONICAL_INDEXES:
        name, table_name, _columns, _unique, _predicate = spec
        actual = _indexes(bind, table_name).get(name)
        if actual is None or not _matches(actual, spec):
            raise RuntimeError(f'0011 post-validation missing canonical index {table_name}.{name}')


def upgrade() -> None:
    bind = op.get_bind()
    _preflight_evidence_tables(bind)
    _preflight_empty_ownership_table(bind)
    _preflight_indexes(bind)
    _preflight_receipts(bind)
    _preflight_active_media(bind)
    _create_evidence_tables()
    _dedupe_receipts(bind)
    _create_missing_canonical_indexes(bind)
    _retire_replaced_indexes(bind)
    _postvalidate(bind)
    _record_completion_sentinel(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _preflight_evidence_tables(bind)
    rows = _validated_current_ownership_rows(bind)
    _preflight_downgrade_objects(bind, rows)
    for row, spec in rows:
        if row['action'] != 'removed_retired':
            continue
        if spec[0] not in _indexes(bind, spec[1]):
            if bind.dialect.name == 'postgresql' and spec[0] == 'user_preferences_user_id_key':
                bind.execute(sa.text(
                    f'ALTER TABLE {_q(spec[1])} ADD CONSTRAINT {_q(spec[0])} UNIQUE ({", ".join(_q(c) for c in spec[2])})'
                ))
            else:
                _create_index(bind, spec)
    for row, spec in reversed(rows):
        if row['action'] != 'created_canonical':
            continue
        actual = _indexes(bind, spec[1]).get(spec[0])
        if actual is None:
            continue
        _drop_index(bind, spec[0], spec[1])
    bind.execute(sa.text(f'DELETE FROM {_q(INDEX_EVIDENCE_TABLE)} WHERE migration_revision = :revision'), {'revision': revision})
