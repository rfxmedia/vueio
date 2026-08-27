from __future__ import annotations

import time
import logging

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .database_indexes import canonical_index_specs
from .schema_migrations import (
    adopt_existing_sqlite_schema,
    alembic_config,
    migration_connection,
    run_alembic_upgrade,
    verify_alembic_head,
    verify_schema_contract,
)

settings = get_settings()
logger = logging.getLogger('vueio.db')


def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set SQLite performance pragmas on each connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.execute('PRAGMA cache_size=-64000')
    cursor.execute('PRAGMA temp_store=MEMORY')
    cursor.close()


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == 'sqlite'


def _engine_kwargs_for_url(database_url: str) -> dict:
    if _is_sqlite_url(database_url):
        return {'connect_args': {'check_same_thread': False}}
    return {}


def _create_database_engine(database_url: str):
    created_engine = create_engine(database_url, **_engine_kwargs_for_url(database_url))
    if _is_sqlite_url(database_url):
        event.listen(created_engine, 'connect', set_sqlite_pragma)
    return created_engine


engine = _create_database_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


POSTGRES_BASELINE_REVISION = '20260329_0001'
POSTGRES_ADOPTION_REPAIR_PATH = (
    'Repair the PostgreSQL schema before startup: restore the missing objects '
    'from backup, apply the owning Alembic migration manually, or restore a '
    'correct alembic_version row for the schema revision you know is present; '
    'then rerun startup migrations.'
)

POSTGRES_BASE_REQUIRED_COLUMNS: dict[str, set[str]] = {
    'activity_log': {'id', 'user_id', 'user_name', 'action', 'entity_type', 'entity_id', 'entity_title', 'details', 'created_at'},
    'agent_api_keys': {'id', 'name', 'user_id', 'key_prefix', 'secret_hash', 'encrypted_token', 'scopes_json', 'is_active', 'created_by', 'created_at', 'updated_at', 'last_used_at', 'revoked_at'},
    'app_identity': {'id', 'team_name', 'website_url', 'logo_upload_name', 'updated_by', 'created_at', 'updated_at'},
    'app_theme': {'id', 'colors_json', 'updated_by', 'created_at', 'updated_at'},
    'comments': {'id', 'file_path', 'project_id', 'horizons_media_asset_id', 'horizons_shot_version_id', 'user_name', 'timestamp', 'text', 'resolved', 'created_at', 'parent_comment_id', 'root_comment_id', 'annotation_data', 'attachments_data'},
    'download_events': {'id', 'created_at', 'user_id', 'user_name', 'source', 'auth_mode', 'share_id', 'project_id', 'tracker_id', 'event_type', 'resource_type', 'resource_id', 'resource_name', 'filename', 'paths_json', 'size_bytes', 'status', 'ip_address', 'ip_chain_json', 'geo_json', 'device_json', 'request_json', 'client_json', 'metadata_json'},
    'horizons_pages': {'id', 'project_id', 'slug', 'title', 'description', 'cover_path', 'blocks_json', 'created_by', 'created_at', 'updated_at'},
    'horizons_project_grants': {'id', 'project_id', 'subject_type', 'subject_id', 'role', 'created_at', 'updated_at'},
    'horizons_projects': {'id', 'slug', 'title', 'description', 'status', 'visibility', 'created_by', 'created_at', 'updated_at', 'due_date', 'thumbnail_path'},
    'horizons_shot_assignees': {'id', 'project_id', 'tracker_id', 'shot_id', 'user_id', 'sort_order', 'created_by', 'created_at', 'updated_at'},
    'horizons_shot_versions': {'id', 'project_id', 'tracker_id', 'shot_id', 'label', 'media_asset_id', 'notes', 'created_by', 'created_at', 'updated_at'},
    'horizons_shots': {'id', 'project_id', 'tracker_id', 'shot_code', 'description', 'status', 'category', 'assignee_user_id', 'latest_version_label', 'latest_media_asset_id', 'created_at', 'updated_at'},
    'horizons_trackers': {'id', 'project_id', 'slug', 'name', 'stats_json', 'stats_updated_at', 'created_at', 'updated_at'},
    'media_assets': {'id', 'project_id', 'file_path', 'storage_scope', 'content_hash', 'file_size', 'modified_at', 'created_at', 'updated_at'},
    'media_metadata': {'cache_identity', 'media_asset_id', 'file_path', 'file_size', 'modified_at', 'info_json', 'created_at', 'updated_at'},
    'notification_deliveries': {'id', 'tracker_event_id', 'recipient_user_id', 'subscription_id', 'provider', 'status', 'attempts', 'next_attempt_at', 'sent_at', 'last_error', 'payload_json', 'created_at', 'updated_at'},
    'notification_preferences': {'user_id', 'default_scope', 'event_types_json', 'channels_json', 'created_at', 'updated_at'},
    'notification_read_state': {'id', 'user_id', 'feed_key', 'last_seen_event_id', 'last_seen_created_at', 'created_at', 'updated_at'},
    'notification_subscriptions': {'id', 'provider', 'recipient_user_id', 'destination', 'scope', 'project_filters_json', 'event_filters_json', 'config_json', 'is_enabled', 'created_by', 'created_at', 'updated_at'},
    'recently_viewed': {'id', 'user_id', 'item_type', 'item_id', 'project_id', 'title', 'subtitle', 'viewed_at'},
    'shares': {'id', 'path', 'is_folder', 'share_type', 'project_id', 'tracker_name', 'page_id', 'created_by', 'created_at', 'expires_at', 'password_hash', 'is_active', 'access_count', 'last_accessed', 'allow_download', 'allow_upload'},
    'shot_registry': {'id', 'project_id', 'tracker_name', 'shot_id', 'status', 'description', 'category', 'latest_version_number', 'latest_file_path', 'latest_media_asset_id', 'source', 'created_at', 'updated_at'},
    'tracker_events': {'id', 'project_id', 'tracker_id', 'shot_id', 'shot_version_id', 'comment_id', 'event_type', 'actor_id', 'actor_name', 'source', 'payload_json', 'created_at'},
    'transcodes': {'id', 'file_path', 'status', 'output_path', 'progress', 'duration', 'created_at'},
    'upload_items': {'id', 'session_id', 'rel_path', 'original_name', 'mime_type', 'size_bytes', 'bytes_received', 'temp_path', 'final_path', 'status', 'error_text', 'created_at', 'updated_at', 'completed_at'},
    'upload_sessions': {'id', 'scope_type', 'share_id', 'project_id', 'base_path', 'uploader_name', 'client_batch_id', 'status', 'created_at', 'updated_at', 'last_activity_at', 'expires_at'},
    'user_preferences': {'id', 'user_id', 'mc_layout', 'created_at', 'updated_at'},
    'user_sessions': {'id', 'user_id', 'created_at', 'last_accessed', 'expires_at'},
    'version_registry': {'id', 'project_id', 'tracker_name', 'shot_id', 'variant_id', 'version_number', 'file_path', 'media_asset_id', 'source', 'created_at', 'updated_at'},
}


def _canonical_adoption_indexes() -> dict[str, set[str]]:
    indexes: dict[str, set[str]] = {}
    for index_name, table_name, _columns, _unique, _predicate in canonical_index_specs():
        indexes.setdefault(table_name, set()).add(index_name)
    return indexes

POSTGRES_ADOPTION_STEPS: tuple[dict[str, object], ...] = (
    {
        'revision': '20260623_0002',
        'stamp_before': POSTGRES_BASELINE_REVISION,
        'columns': {'comments': {'annotation_target'}},
        'indexes': {},
    },
    {
        'revision': '20260705_0003',
        'stamp_before': '20260623_0002',
        'columns': {
            'horizons_trackers': {'tags_json'},
            'horizons_shots': {'archived_at', 'archived_by', 'archive_reason'},
        },
        'indexes': {'horizons_shots': {'idx_horizons_shots_project_tracker_archived'}},
    },
    {
        'revision': '20260712_0004',
        'stamp_before': '20260705_0003',
        'columns': {
            'shares': {'tracker_id'},
            'version_registry': {'tracker_id'},
            'shot_registry': {'tracker_id'},
        },
        'indexes': {
            'shares': {'idx_shares_project_tracker'},
            'version_registry': {'idx_version_registry_project_tracker_id'},
            'shot_registry': {'idx_shot_registry_project_tracker_id'},
        },
    },
    {
        'revision': '20260713_0005',
        'stamp_before': '20260712_0004',
        'columns': {
            'media_assets': {'source_signature', 'unavailable_at', 'unavailable_reason'},
            'shares': {'media_asset_id'},
        },
        'indexes': {
            'media_assets': {'idx_media_assets_source_signature', 'idx_media_assets_unavailable_at', 'idx_media_assets_project_scope_path_available'},
            'shares': {'idx_shares_media_asset_id'},
        },
    },
    {
        'revision': '20260713_0006',
        'stamp_before': '20260713_0005',
        'columns': {},
        'indexes': {'media_assets': {'uq_media_assets_active_owner_scope_path'}},
        'owned_tables': {
            'media_asset_duplicate_retire_audit': {
                'id',
                'migration_revision',
                'media_asset_id',
                'previous_unavailable_at',
                'previous_unavailable_reason',
                'previous_updated_at',
                'created_at',
            },
        },
    },
    {
        'revision': '20260713_0007',
        'stamp_before': '20260713_0006',
        'columns': {},
        'indexes': {
            'file_operation_journal': {
                'idx_file_operation_journal_operation_type',
                'idx_file_operation_journal_project_id',
                'idx_file_operation_journal_status',
            },
        },
        'owned_tables': {
            'file_operation_journal': {
                'id',
                'operation_type',
                'project_id',
                'source_path',
                'destination_path',
                'status',
                'payload_json',
                'error_text',
                'created_at',
                'updated_at',
            },
        },
    },
    {
        'revision': '20260713_0008',
        'stamp_before': '20260713_0007',
        'columns': {},
        'indexes': {'agent_mutation_receipts': {'uq_agent_mutation_receipts_key_operation_idempotency'}},
        'owned_tables': {
            'agent_mutation_receipts': {'id', 'agent_key_id', 'operation', 'idempotency_key', 'response_json', 'created_at'},
        },
    },
    {
        'revision': '20260713_0009',
        'stamp_before': '20260713_0008',
        'columns': {},
        'indexes': {},
        'owned_tables': {
            'stale_share_field_retirement_audit': {
                'id', 'migration_revision', 'share_id', 'field_name', 'source_dialect',
                'source_column_type', 'source_column_nullable', 'source_column_default',
                'value_type', 'value_text', 'value_integer', 'value_boolean', 'evidence_created_at',
            },
        },
    },
    {
        'revision': '20260713_0011',
        'stamp_before': '20260713_0010',
        'columns': {},
        'indexes': _canonical_adoption_indexes(),
        'owned_tables': {
            'alembic_0011_index_ownership': {
                'id', 'migration_revision', 'action', 'object_name', 'table_name',
                'columns_csv', 'is_unique', 'predicate', 'dialect',
            },
            'alembic_0011_receipt_dedupe_audit': {
                'audit_id', 'migration_revision', 'canonical_receipt_id', 'id',
                'agent_key_id', 'operation', 'idempotency_key', 'response_json', 'created_at',
            },
        },
    },
    {
        'revision': '20260719_0013',
        'stamp_before': '20260713_0012',
        'columns': {'horizons_trackers': {'settings_json'}},
        'indexes': {},
    },
    {
        'revision': '20260720_0014',
        'stamp_before': '20260719_0013',
        'columns': {'horizons_projects': {'storage_root', 'storage_path'}},
        'indexes': {'horizons_projects': {'ix_horizons_projects_storage_root'}},
    },
    {
        'revision': '20260722_0015',
        'stamp_before': '20260720_0014',
        'columns': {'media_assets': {'artifact_identity'}},
        'indexes': {},
    },
    {
        'revision': '20260728_0016',
        'stamp_before': '20260722_0015',
        'columns': {'shares': {'request_files'}},
        'indexes': {},
    },
    {
        'revision': '20260729_0017',
        'stamp_before': '20260728_0016',
        'columns': {'horizons_shot_versions': {'share_state', 'published_at'}},
        'indexes': {},
    },
    {
        'revision': '20260731_0018',
        'stamp_before': '20260729_0017',
        'columns': {'upload_sessions': {'owner_user_id'}},
        'indexes': {'upload_sessions': {'ix_upload_sessions_owner_user_id'}},
    },
    {
        'revision': '20260731_0019',
        'stamp_before': '20260731_0018',
        'columns': {},
        'indexes': {
            'package_jobs': {
                'ix_package_jobs_status',
                'ix_package_jobs_owner_type',
                'ix_package_jobs_owner_id',
                'ix_package_jobs_project_id',
                'ix_package_jobs_updated_at',
                'ix_package_jobs_expires_at',
            },
        },
        'owned_tables': {
            'package_jobs': {
                'id',
                'kind',
                'status',
                'filename',
                'artifact_path',
                'total_bytes',
                'packaged_bytes',
                'file_count',
                'packaged_files',
                'progress',
                'message',
                'error',
                'owner_type',
                'owner_id',
                'project_id',
                'authorization_json',
                'created_at',
                'updated_at',
                'expires_at',
            },
        },
    },
    {
        'revision': '20260731_0020',
        'stamp_before': '20260731_0019',
        'columns': {'transcodes': {'last_accessed'}},
        'indexes': {'transcodes': {'ix_transcodes_last_accessed'}},
    },
    {
        'revision': '20260810_0021',
        'stamp_before': '20260731_0020',
        'columns': {},
        'indexes': {
            'tracker_view_events': {
                'ix_tracker_view_events_history',
                'ix_tracker_view_events_presence',
                'ix_tracker_view_events_visit',
                'ix_tracker_view_events_created_at',
            },
        },
        'owned_tables': {
            'tracker_view_events': {
                'id',
                'project_id',
                'tracker_id',
                'shot_id',
                'shot_version_id',
                'visit_id',
                'viewer_user_id',
                'viewer_name',
                'source',
                'share_id',
                'event_type',
                'device_type',
                'client_metadata_json',
                'created_at',
                'last_seen_at',
            },
        },
    },
    {
        'revision': '20260823_0022',
        'stamp_before': '20260810_0021',
        'columns': {'tracker_events': {'undo_of_event_id'}},
        'indexes': {'tracker_events': {'uq_tracker_events_undo_of_event_id'}},
    },
    {
        'revision': '20260824_0023',
        'stamp_before': '20260823_0022',
        'columns': {'tracker_events': {'state_snapshot', 'state_hash'}},
        'indexes': {},
    },
)


def _postgres_index_names(inspector, table_name: str) -> set[str]:
    index_names = {index['name'] for index in inspector.get_indexes(table_name)}
    index_names.update(constraint['name'] for constraint in inspector.get_unique_constraints(table_name) if constraint.get('name'))
    return index_names


def _postgres_table_columns(inspector, table_name: str) -> set[str]:
    return {column['name'] for column in inspector.get_columns(table_name)}


def _format_missing_schema_items(items: list[str]) -> str:
    return ', '.join(sorted(items))


def _raise_postgres_adoption_error(items: list[str]) -> None:
    missing = _format_missing_schema_items(items)
    raise RuntimeError(
        f'Cannot safely adopt existing PostgreSQL schema without alembic_version; '
        f'missing required objects: {missing}. {POSTGRES_ADOPTION_REPAIR_PATH}'
    )


def _select_postgres_adoption_revision(inspector) -> str:
    tables = set(inspector.get_table_names())
    repairable_tables = {
        table_name
        for step in POSTGRES_ADOPTION_STEPS
        for table_name in (step.get('owned_tables') or {})
    }
    missing_required = [
        f'table {table_name}'
        for table_name in POSTGRES_BASE_REQUIRED_COLUMNS
        if table_name not in tables and table_name not in repairable_tables
    ]
    for table_name, required_columns in POSTGRES_BASE_REQUIRED_COLUMNS.items():
        if table_name not in tables:
            continue
        missing_columns = required_columns - _postgres_table_columns(inspector, table_name)
        missing_required.extend(f'{table_name}.{column_name}' for column_name in missing_columns)
    for step in POSTGRES_ADOPTION_STEPS:
        for table_name, required_columns in (step.get('owned_tables') or {}).items():
            if table_name in tables and not set(required_columns).issubset(_postgres_table_columns(inspector, table_name)):
                missing_required.append(f'table {table_name} is partially present')
    if missing_required:
        _raise_postgres_adoption_error(missing_required)

    for step in POSTGRES_ADOPTION_STEPS:
        for table_name, required_columns in (step.get('columns') or {}).items():
            if table_name in tables and not set(required_columns).issubset(_postgres_table_columns(inspector, table_name)):
                return str(step['stamp_before'])
        for table_name, required_columns in (step.get('owned_tables') or {}).items():
            if table_name not in tables:
                return str(step['stamp_before'])
            if not set(required_columns).issubset(_postgres_table_columns(inspector, table_name)):
                return str(step['stamp_before'])
        for table_name, required_indexes in (step.get('indexes') or {}).items():
            if table_name in tables and not set(required_indexes).issubset(_postgres_index_names(inspector, table_name)):
                return str(step['stamp_before'])
    return 'head'


def _adopt_existing_postgres_schema_for_alembic(conn) -> None:
    from alembic import command

    inspector = inspect(conn)
    if inspector.has_table('alembic_version'):
        current_revision = conn.execute(text('SELECT version_num FROM alembic_version LIMIT 1')).scalar()
        if current_revision:
            return
    app_tables = set(inspector.get_table_names())
    repairable_tables = {
        table_name
        for step in POSTGRES_ADOPTION_STEPS
        for table_name in (step.get('owned_tables') or {})
    }
    if not app_tables.intersection(set(POSTGRES_BASE_REQUIRED_COLUMNS) | repairable_tables):
        return
    command.stamp(alembic_config(conn), _select_postgres_adoption_revision(inspector))


def _cleanup_expired_sessions(conn) -> None:
    conn.execute(text('DELETE FROM user_sessions WHERE expires_at < :now'), {'now': time.time()})


def _ensure_legacy_agent_key(conn) -> None:
    if not settings.VUEIO_AGENT_API_KEY:
        return
    inspector = inspect(conn)
    if not inspector.has_table('agent_api_keys'):
        logger.warning('agent_api_keys table is missing; skipping legacy env agent key import')
        return

    import hashlib
    import uuid

    legacy_hash = hashlib.sha256(settings.VUEIO_AGENT_API_KEY.encode()).hexdigest()
    savepoint = conn.begin_nested()
    try:
        existing = conn.execute(text('SELECT id FROM agent_api_keys WHERE secret_hash = :secret_hash LIMIT 1'), {'secret_hash': legacy_hash}).fetchone()
        if existing:
            savepoint.commit()
            return

        created_at = time.time()
        conn.execute(
            text("""
                INSERT INTO agent_api_keys (
                    id, name, user_id, key_prefix, secret_hash, encrypted_token, scopes_json, is_active,
                    created_by, created_at, updated_at, revoked_at
                ) VALUES (
                    :id, :name, :user_id, :key_prefix, :secret_hash, :encrypted_token, :scopes_json, :is_active,
                    :created_by, :created_at, :updated_at, NULL
                )
            """),
            {
                'id': f'legacy-{uuid.uuid4()}',
                'name': 'Imported legacy env agent key',
                'user_id': settings.VUEIO_AGENT_USER or 'admin',
                'key_prefix': settings.VUEIO_AGENT_API_KEY[:12],
                'secret_hash': legacy_hash,
                'encrypted_token': None,
                'scopes_json': '[]',
                'is_active': True,
                'created_by': 'system-migration',
                'created_at': created_at,
                'updated_at': created_at,
            },
        )
    except Exception:
        savepoint.rollback()
        logger.exception('Failed to import legacy env agent key; startup will continue without importing it')
        return
    savepoint.commit()
    logger.info('Imported legacy env agent key into DB registry')


def run_migrations() -> None:
    """Upgrade and verify the schema before application routes are created."""
    with migration_connection(engine) as conn:
        if engine.dialect.name == 'sqlite':
            adopt_existing_sqlite_schema(conn)
        else:
            _adopt_existing_postgres_schema_for_alembic(conn)
        run_alembic_upgrade(conn)
        verify_alembic_head(conn)
        verify_schema_contract(conn)
        _cleanup_expired_sessions(conn)
        _ensure_legacy_agent_key(conn)
    return




def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
