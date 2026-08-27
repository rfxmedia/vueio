from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    HorizonProject,
    HorizonShot,
    HorizonShotAssignee,
    HorizonTracker,
    NotificationDelivery,
    NotificationPreference,
    NotificationReadState,
    NotificationSubscription,
    TrackerEvent,
)
from app.services.auth import load_users
from app.services.external_urls import normalize_external_http_url, normalize_http_origin
from app.services.horizons_fresh import (
    get_horizon_project_access_role,
    is_restricted_horizon_artist,
    list_visible_horizon_projects,
)
from app.services.tracker_events import serialize_tracker_event, tracker_activity_visible_shot_ids

logger = logging.getLogger('vueio.notifications')
settings = get_settings()

NOTIFICATION_SCOPES = {'all_visible', 'related_to_me'}
NOTIFICATION_PROVIDERS = {'discord'}
DELIVERY_STATUSES = {'pending', 'sending', 'sent', 'failed'}
DISPATCH_INTERVAL_SECONDS = 8
MAX_DELIVERY_ATTEMPTS = 8

EVENT_BUCKETS = {
    'version_added': 'versions',
    'versions_bulk_updated': 'versions',
    'version_published': 'versions',
    'version_kept_internal': 'versions',
    'version_removed_from_shares': 'versions',
    'brief_file_uploaded': 'versions',
    'shots_imported': 'versions',
    'comment_added': 'comments',
    'comment_resolved': 'comments',
    'comment_deleted': 'comments',
    'assignee_changed': 'assignments',
    'status_changed': 'status',
    'status_changed_bulk': 'status',
    'download_started': 'downloads',
}

DEFAULT_CHANNELS = {
    'in_app': True,
    'discord': True,
    'email': False,
    'telegram': False,
    'whatsapp': False,
}

_dispatcher_started = False
_dispatcher_lock = threading.Lock()
DISCORD_BOT_PERMISSIONS = 84992


def _event_audience(user: dict, access_role: str | None) -> str:
    return 'restricted' if is_restricted_horizon_artist(user, access_role) else 'internal'


def _provider_settings_path():
    return settings.notification_provider_settings_file


def _load_provider_settings() -> dict[str, Any]:
    path = _provider_settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        logger.warning('Failed to read notification provider settings', exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _save_provider_settings(data: dict[str, Any]) -> None:
    path = _provider_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f'{path.suffix}.tmp')
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    os.chmod(tmp_path, 0o600)
    tmp_path.replace(path)


def _discord_provider_settings() -> dict[str, Any]:
    providers = _load_provider_settings()
    discord = providers.get('discord') if isinstance(providers, dict) else {}
    return discord if isinstance(discord, dict) else {}


def _discord_token() -> str:
    configured = str(_discord_provider_settings().get('bot_token') or '').strip()
    return configured or (settings.DISCORD_BOT_TOKEN or '').strip()


def is_discord_provider_configured() -> bool:
    return bool(_discord_token())


def _discord_application_id() -> str:
    return str(_discord_provider_settings().get('application_id') or '').strip()


def _normalize_discord_channel_id(value: object) -> str:
    destination = str(value or '').strip()
    if not destination.isdigit() or not 1 <= len(destination) <= 20:
        return ''
    return destination


def _normalize_public_base_url(value: object) -> str:
    return normalize_http_origin(value)


def get_discord_provider_settings() -> dict[str, Any]:
    discord = _discord_provider_settings()
    token = _discord_token()
    base_url = _public_base_url()
    application_id = _discord_application_id()
    invite_url = ''
    if application_id:
        invite_url = (
            f'https://discord.com/oauth2/authorize?client_id={application_id}'
            f'&permissions={DISCORD_BOT_PERMISSIONS}&integration_type=0&scope=bot'
        )
    return {
        'provider': 'discord',
        'is_configured': bool(token),
        'has_saved_token': bool(str(discord.get('bot_token') or '').strip()),
        'uses_env_token': bool((settings.DISCORD_BOT_TOKEN or '').strip()),
        'public_base_url': base_url,
        'application_id': application_id,
        'bot_permissions': DISCORD_BOT_PERMISSIONS,
        'invite_url': invite_url,
    }


def save_discord_provider_settings(payload: dict[str, Any]) -> dict[str, Any]:
    providers = _load_provider_settings()
    discord = providers.get('discord') if isinstance(providers.get('discord'), dict) else {}

    if 'application_id' in payload:
        application_id = str(payload.get('application_id') or '').strip()
        if application_id and not application_id.isdigit():
            raise HTTPException(status_code=400, detail='Discord application ID must be numeric')
        discord['application_id'] = application_id

    if 'public_base_url' in payload:
        raw_public_base_url = str(payload.get('public_base_url') or '').strip().rstrip('/')
        public_base_url = _normalize_public_base_url(raw_public_base_url) if raw_public_base_url else ''
        if raw_public_base_url and not public_base_url:
            raise HTTPException(status_code=400, detail='Public base URL must be a valid http or https URL')
        discord['public_base_url'] = public_base_url

    token_value = payload.get('bot_token') if 'bot_token' in payload else None
    if token_value is not None:
        token = str(token_value or '').strip()
        if token:
            discord['bot_token'] = token
        elif payload.get('clear_token'):
            discord.pop('bot_token', None)

    providers['discord'] = discord
    _save_provider_settings(providers)
    if is_discord_provider_configured():
        start_notification_dispatcher()
    return get_discord_provider_settings()


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except Exception:
        return fallback
    return parsed if parsed is not None else fallback


def _json_list(value: str | None) -> list[str]:
    parsed = _json_loads(value, [])
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item or '').strip()]


def _json_dict(value: str | None) -> dict[str, Any]:
    parsed = _json_loads(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _user_id(user: dict | None) -> str:
    return str((user or {}).get('id') or (user or {}).get('username') or '').strip()


def _subject_ids_for_user(user: dict | None) -> set[str]:
    return {
        str(value).strip()
        for value in [(user or {}).get('id'), (user or {}).get('username')]
        if str(value or '').strip()
    }


def _default_scope_for_user(user: dict | None) -> str:
    return 'all_visible' if (user or {}).get('role') == 'admin' else 'related_to_me'


def normalize_notification_scope(scope: str | None, user: dict | None = None) -> str:
    value = (scope or '').strip()
    if value == 'default' or not value:
        return _default_scope_for_user(user)
    if value not in NOTIFICATION_SCOPES:
        raise HTTPException(status_code=400, detail='Invalid notification scope')
    return value


def notification_bucket_for_event(event_type: str | None) -> str:
    return EVENT_BUCKETS.get(event_type or '', 'updates')


def _event_filter_matches(event_type: str, filter_value: str | None) -> bool:
    if event_type == 'tracker_checkpoint':
        return False
    value = (filter_value or 'all').strip()
    if value in {'', 'all'}:
        return True
    if value in {'comments', 'status', 'assignments', 'versions', 'downloads', 'updates'}:
        return notification_bucket_for_event(event_type) == value
    return event_type == value


def _normalize_channels(raw: dict | None) -> dict[str, bool]:
    channels = dict(DEFAULT_CHANNELS)
    if isinstance(raw, dict):
        for key in DEFAULT_CHANNELS:
            if key in raw:
                channels[key] = bool(raw.get(key))
    return channels


def _normalize_event_types(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        value = str(entry or '').strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def default_notification_preferences_for_user(user_id: str, user: dict | None = None) -> dict[str, Any]:
    return {
        'user_id': user_id,
        'default_scope': _default_scope_for_user(user),
        'event_types': [],
        'channels': dict(DEFAULT_CHANNELS),
        'created_at': None,
        'updated_at': None,
    }


def get_notification_preferences(db: Session, user_id: str, user: dict | None = None) -> NotificationPreference | None:
    normalized_user_id = str(user_id or '').strip()
    if not normalized_user_id:
        return None
    return db.query(NotificationPreference).filter(NotificationPreference.user_id == normalized_user_id).first()


def default_notification_scope(db: Session, user: dict | None = None) -> str:
    user_id = _user_id(user)
    record = get_notification_preferences(db, user_id, user) if user_id else None
    if record and record.default_scope in NOTIFICATION_SCOPES:
        return record.default_scope
    return _default_scope_for_user(user)


def resolve_notification_scope(db: Session, scope: str | None, user: dict | None = None) -> str:
    value = (scope or '').strip()
    if value == 'default' or not value:
        return default_notification_scope(db, user)
    return normalize_notification_scope(value, user)


def serialize_notification_preferences(record: NotificationPreference | None, user_id: str, user: dict | None = None) -> dict[str, Any]:
    if record is None:
        return default_notification_preferences_for_user(user_id, user)
    return {
        'user_id': record.user_id,
        'default_scope': normalize_notification_scope(record.default_scope, user),
        'event_types': _json_list(record.event_types_json),
        'channels': _normalize_channels(_json_dict(record.channels_json)),
        'created_at': record.created_at,
        'updated_at': record.updated_at,
    }


def save_notification_preferences(db: Session, user: dict, payload: dict[str, Any]) -> dict[str, Any]:
    user_id = _user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail='Authentication required')

    now = time.time()
    record = get_notification_preferences(db, user_id, user)
    current = serialize_notification_preferences(record, user_id, user)
    if record is None:
        record = NotificationPreference(user_id=user_id, created_at=now)

    next_channels = current['channels']
    if 'channels' in payload:
        next_channels = {**next_channels, **(payload.get('channels') or {})}

    record.default_scope = normalize_notification_scope(payload.get('default_scope', current['default_scope']), user)
    record.event_types_json = json.dumps(_normalize_event_types(payload.get('event_types', current['event_types'])))
    record.channels_json = json.dumps(_normalize_channels(next_channels))
    record.updated_at = now
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_notification_preferences(record, user_id, user)


def _channel_enabled_for_user(db: Session, user: dict, provider: str, event_type: str) -> bool:
    user_id = _user_id(user)
    prefs = serialize_notification_preferences(get_notification_preferences(db, user_id, user), user_id, user)
    if not prefs['channels'].get(provider, False):
        return False
    enabled_event_types = prefs.get('event_types') or []
    event_bucket = notification_bucket_for_event(event_type)
    return not enabled_event_types or event_type in enabled_event_types or event_bucket in enabled_event_types


def feed_key_for(scope: str, filter_value: str | None = None) -> str:
    normalized_filter = (filter_value or 'all').strip() or 'all'
    return f'{scope}:{normalized_filter}'


def get_read_state(db: Session, user_id: str, feed_key: str) -> NotificationReadState | None:
    return (
        db.query(NotificationReadState)
        .filter(NotificationReadState.user_id == user_id)
        .filter(NotificationReadState.feed_key == feed_key)
        .first()
    )


def serialize_read_state(record: NotificationReadState | None, user_id: str, feed_key: str) -> dict[str, Any]:
    if record is None:
        return {
            'user_id': user_id,
            'feed_key': feed_key,
            'last_seen_event_id': None,
            'last_seen_created_at': 0,
        }
    return {
        'user_id': record.user_id,
        'feed_key': record.feed_key,
        'last_seen_event_id': record.last_seen_event_id,
        'last_seen_created_at': record.last_seen_created_at or 0,
    }


def mark_notification_read(db: Session, user: dict, *, event_id: int | None, scope: str | None, filter_value: str | None) -> dict[str, Any]:
    user_id = _user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    normalized_scope = resolve_notification_scope(db, scope, user)
    feed_key = feed_key_for(normalized_scope, filter_value)
    event = db.query(TrackerEvent).filter(TrackerEvent.id == event_id).first() if event_id else None
    if event_id and event is None:
        raise HTTPException(status_code=404, detail='Notification event not found')
    if event is not None and not _notification_event_is_feed_visible(
        db,
        event=event,
        user=user,
        scope=normalized_scope,
        filter_value=filter_value,
    ):
        raise HTTPException(status_code=404, detail='Notification event not found')

    now = time.time()
    record = get_read_state(db, user_id, feed_key)
    if record is None:
        record = NotificationReadState(user_id=user_id, feed_key=feed_key, created_at=now)

    if event is not None:
        record.last_seen_event_id = event.id
        record.last_seen_created_at = event.created_at or 0
    else:
        record.last_seen_created_at = now
    record.updated_at = now
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_read_state(record, user_id, feed_key)


def _assigned_shot_ids_for_user(db: Session, *, project_id: str, tracker_id: str, user: dict) -> set[str]:
    subject_ids = _subject_ids_for_user(user)
    if not subject_ids:
        return set()
    return {
        shot_id
        for (shot_id,) in (
            db.query(HorizonShot.id)
            .join(HorizonShotAssignee, HorizonShotAssignee.shot_id == HorizonShot.id)
            .filter(HorizonShot.project_id == project_id)
            .filter(HorizonShot.tracker_id == tracker_id)
            .filter(HorizonShotAssignee.user_id.in_(subject_ids))
            .distinct()
            .all()
        )
    }


def _visible_shot_ids_for_scope(db: Session, *, project_id: str, tracker_id: str, user: dict, access_role: str | None, scope: str) -> set[str] | None:
    if scope == 'related_to_me':
        return _assigned_shot_ids_for_user(db, project_id=project_id, tracker_id=tracker_id, user=user)
    return tracker_activity_visible_shot_ids(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
        user=user,
        access_role=access_role,
    )


def _event_has_related_target(event: TrackerEvent, visible_shot_ids: set[str] | None) -> bool:
    if visible_shot_ids is None:
        return True
    if event.shot_id:
        return event.shot_id in visible_shot_ids
    payload = _json_dict(event.payload_json)
    shots = payload.get('shots')
    if isinstance(shots, list):
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            shot_id = str(shot.get('shot_id') or shot.get('id') or '').strip()
            if shot_id in visible_shot_ids:
                return True
    return False


def _notification_event_is_feed_visible(
    db: Session,
    *,
    event: TrackerEvent,
    user: dict,
    scope: str,
    filter_value: str | None,
) -> bool:
    if not _event_filter_matches(event.event_type, filter_value):
        return False
    if not _channel_enabled_for_user(db, user, 'in_app', event.event_type):
        return False

    project = db.query(HorizonProject).filter(HorizonProject.id == event.project_id).first()
    tracker = (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == event.project_id)
        .filter(HorizonTracker.id == event.tracker_id)
        .first()
    )
    if project is None or tracker is None:
        return False
    access_role = get_horizon_project_access_role(db, project, user)
    if access_role is None:
        return False

    visible_shot_ids = _visible_shot_ids_for_scope(
        db,
        project_id=event.project_id,
        tracker_id=event.tracker_id,
        user=user,
        access_role=access_role,
        scope=scope,
    )
    if scope == 'related_to_me' and not _event_has_related_target(event, visible_shot_ids):
        return False
    return serialize_tracker_event(
        event,
        visible_shot_ids=visible_shot_ids,
        audience=_event_audience(user, access_role),
    ) is not None


def _cursor_filter(query, before_created_at: float | None, before_id: int | None):
    if before_created_at is None:
        return query
    if before_id is None:
        return query.filter(TrackerEvent.created_at < before_created_at)
    return query.filter(
        or_(
            TrackerEvent.created_at < before_created_at,
            and_(TrackerEvent.created_at == before_created_at, TrackerEvent.id < before_id),
        )
    )


def _public_base_url() -> str:
    configured = _normalize_public_base_url(_discord_provider_settings().get('public_base_url'))
    return configured or _normalize_public_base_url(settings.VUEIO_PUBLIC_BASE_URL)


def _tracker_path(project_id: str, tracker_name: str | None) -> str:
    encoded_project_id = quote(str(project_id or ''), safe='')
    encoded_tracker_name = quote(str(tracker_name or ''), safe='')
    return f'/projects/{encoded_project_id}/t/{encoded_tracker_name}'


def _add_notification_metadata(item: dict[str, Any], project: HorizonProject, tracker: HorizonTracker) -> dict[str, Any]:
    item['project_title'] = project.title
    item['project_slug'] = project.slug
    item['project_thumbnail_path'] = project.thumbnail_path
    item['tracker_name'] = tracker.name
    item['tracker_slug'] = tracker.slug
    item['bucket'] = notification_bucket_for_event(item.get('event_type'))
    item['created_at_iso'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(float(item.get('created_at') or 0)))
    path = _tracker_path(item['project_id'], tracker.name)
    item['target_path'] = path
    base_url = _public_base_url()
    if base_url:
        item['target_url'] = f'{base_url}{path}'
    if isinstance(item.get('target'), dict):
        item['target']['tracker_ref'] = tracker.name
        item['target']['tracker_slug'] = tracker.slug
        item['target']['path'] = path
        if base_url:
            item['target']['url'] = f'{base_url}{path}'
    return item


def list_notification_feed(
    db: Session,
    *,
    user: dict,
    auth_mode: str | None = None,
    limit: int | None = None,
    calendar_days: int | None = None,
    before_created_at: float | None = None,
    before_id: int | None = None,
    filter_value: str | None = None,
    scope: str | None = None,
    read_status: str | None = None,
    include_unread: bool = True,
) -> dict[str, Any]:
    user_id = _user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail='Authentication required')

    normalized_scope = resolve_notification_scope(db, scope, user)
    normalized_read_status = str(read_status or 'all').strip().lower()
    if normalized_read_status not in {'all', 'unread', 'read'}:
        raise HTTPException(status_code=400, detail='Invalid notification read status')
    page_limit = max(1, min(int(limit or 40), 100))
    calendar_day_limit = max(0, min(int(calendar_days or 0), 14))
    preferences = serialize_notification_preferences(get_notification_preferences(db, user_id, user), user_id, user)
    feed_key = feed_key_for(normalized_scope, filter_value)
    read_state = get_read_state(db, user_id, feed_key)
    if not preferences['channels'].get('in_app', True):
        return {
            'items': [],
            'next_before_created_at': None,
            'next_before_id': None,
            'next_before': None,
            'read_state': serialize_read_state(read_state, user_id, feed_key),
            'unread_count': 0,
            'scope': normalized_scope,
            'filter': (filter_value or 'all').strip() or 'all',
            'read_status': normalized_read_status,
        }
    enabled_event_types = preferences.get('event_types') or []

    def preference_allows_event(event_type: str) -> bool:
        return (
            not enabled_event_types or
            event_type in enabled_event_types or
            notification_bucket_for_event(event_type) in enabled_event_types
        )

    projects = list_visible_horizon_projects(db, user, auth_mode=auth_mode)
    if not projects:
        return {
            'items': [],
            'next_before_created_at': None,
            'next_before_id': None,
            'next_before': None,
            'read_state': serialize_read_state(read_state, user_id, feed_key),
            'unread_count': 0,
            'scope': normalized_scope,
            'filter': (filter_value or 'all').strip() or 'all',
            'read_status': normalized_read_status,
        }

    project_map = {project.id: project for project in projects}
    access_roles = {
        project.id: get_horizon_project_access_role(db, project, user, auth_mode=auth_mode)
        for project in projects
    }
    trackers = (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id.in_(list(project_map.keys())))
        .all()
    )
    tracker_map = {(tracker.project_id, tracker.id): tracker for tracker in trackers}
    visible_cache: dict[tuple[str, str, str], set[str] | None] = {}

    def visible_shot_ids(project_id: str, tracker_id: str) -> set[str] | None:
        key = (project_id, tracker_id, normalized_scope)
        if key not in visible_cache:
            visible_cache[key] = _visible_shot_ids_for_scope(
                db,
                project_id=project_id,
                tracker_id=tracker_id,
                user=user,
                access_role=access_roles.get(project_id),
                scope=normalized_scope,
            )
        return visible_cache[key]

    items: list[dict[str, Any]] = []
    cursor_created_at = before_created_at
    cursor_id = before_id
    batch_limit = min(max(page_limit * 4, 80), 400)
    next_before_created_at = None
    next_before_id = None
    included_calendar_days: set[str] = set()
    reached_calendar_day_limit = False

    while len(items) < page_limit and not reached_calendar_day_limit:
        query = db.query(TrackerEvent).filter(TrackerEvent.project_id.in_(list(project_map.keys())))
        query = _cursor_filter(query, cursor_created_at, cursor_id)
        rows = (
            query
            .order_by(TrackerEvent.created_at.desc(), TrackerEvent.id.desc())
            .limit(batch_limit)
            .all()
        )
        if not rows:
            break

        for event in rows:
            cursor_created_at = event.created_at
            cursor_id = event.id
            if not _event_filter_matches(event.event_type, filter_value):
                continue
            if not preference_allows_event(event.event_type):
                continue
            if not event_matches_read_status(event, read_state, normalized_read_status):
                continue
            project = project_map.get(event.project_id)
            tracker = tracker_map.get((event.project_id, event.tracker_id))
            if project is None or tracker is None:
                continue
            event_visible_shot_ids = visible_shot_ids(event.project_id, event.tracker_id)
            if normalized_scope == 'related_to_me' and not _event_has_related_target(event, event_visible_shot_ids):
                continue
            serialized = serialize_tracker_event(
                event,
                visible_shot_ids=event_visible_shot_ids,
                audience=_event_audience(user, access_roles.get(event.project_id)),
            )
            if serialized is None:
                continue
            event_day = notification_calendar_day_key(event.created_at)
            if calendar_day_limit and event_day not in included_calendar_days and len(included_calendar_days) >= calendar_day_limit:
                if items:
                    next_before_created_at = items[-1].get('created_at')
                    next_before_id = items[-1].get('id')
                reached_calendar_day_limit = True
                break
            included_calendar_days.add(event_day)
            items.append(_add_notification_metadata(serialized, project, tracker))
            if len(items) == page_limit:
                next_before_created_at = event.created_at
                next_before_id = event.id
                break

        if len(items) == page_limit:
            break
        if reached_calendar_day_limit:
            break
        if len(rows) < batch_limit:
            break

    unread_count = 0
    if include_unread:
        unread_count = count_unread_notifications(
            db,
            user=user,
            auth_mode=auth_mode,
            scope=normalized_scope,
            filter_value=filter_value,
            after_created_at=read_state.last_seen_created_at if read_state else 0,
        )
    return {
        'items': items,
        'next_before_created_at': next_before_created_at,
        'next_before_id': next_before_id,
        'next_before': next_before_created_at,
        'read_state': serialize_read_state(read_state, user_id, feed_key),
        'unread_count': unread_count,
        'scope': normalized_scope,
        'filter': (filter_value or 'all').strip() or 'all',
        'read_status': normalized_read_status,
    }


def notification_calendar_day_key(created_at: float | int | None) -> str:
    try:
        return datetime.fromtimestamp(float(created_at or 0)).strftime('%Y-%m-%d')
    except (OSError, OverflowError, TypeError, ValueError):
        return 'unknown'


def event_matches_read_status(event: TrackerEvent, read_state: NotificationReadState | None, read_status: str) -> bool:
    if read_status == 'all':
        return True
    if not read_state:
        return read_status == 'unread'
    event_created_at = float(event.created_at or 0)
    seen_created_at = float(read_state.last_seen_created_at or 0)
    event_id = int(event.id or 0)
    seen_event_id = int(read_state.last_seen_event_id or 0)
    is_read = event_created_at < seen_created_at or (event_created_at == seen_created_at and event_id <= seen_event_id)
    return is_read if read_status == 'read' else not is_read


def count_unread_notifications(
    db: Session,
    *,
    user: dict,
    auth_mode: str | None,
    scope: str,
    filter_value: str | None,
    after_created_at: float,
) -> int:
    if not after_created_at:
        return min(len(list_notification_feed(
            db,
            user=user,
            auth_mode=auth_mode,
            limit=100,
            filter_value=filter_value,
            scope=scope,
            include_unread=False,
        )['items']), 100)

    response = list_notification_feed(
        db,
        user=user,
        auth_mode=auth_mode,
        limit=100,
        filter_value=filter_value,
        scope=scope,
        include_unread=False,
    )
    return len([item for item in response['items'] if float(item.get('created_at') or 0) > after_created_at])


def _subscription_filters_match(subscription: NotificationSubscription, event: TrackerEvent) -> bool:
    project_filters = set(_json_list(subscription.project_filters_json))
    if project_filters and event.project_id not in project_filters:
        return False
    event_filters = set(_json_list(subscription.event_filters_json))
    return not event_filters or event.event_type in event_filters or notification_bucket_for_event(event.event_type) in event_filters


def _recipient_user(user_id: str) -> dict | None:
    return load_users().get(user_id)


def _event_visible_for_subscription(db: Session, *, subscription: NotificationSubscription, event: TrackerEvent, user: dict) -> dict[str, Any] | None:
    project = db.query(HorizonProject).filter(HorizonProject.id == event.project_id).first()
    tracker = db.query(HorizonTracker).filter(HorizonTracker.project_id == event.project_id).filter(HorizonTracker.id == event.tracker_id).first()
    if project is None or tracker is None:
        return None
    access_role = get_horizon_project_access_role(db, project, user)
    if access_role is None:
        return None
    scope = normalize_notification_scope(subscription.scope, user)
    visible_shot_ids = _visible_shot_ids_for_scope(
        db,
        project_id=event.project_id,
        tracker_id=event.tracker_id,
        user=user,
        access_role=access_role,
        scope=scope,
    )
    if scope == 'related_to_me' and not _event_has_related_target(event, visible_shot_ids):
        return None
    serialized = serialize_tracker_event(
        event,
        visible_shot_ids=visible_shot_ids,
        audience=_event_audience(user, access_role),
    )
    if serialized is None:
        return None
    return _add_notification_metadata(serialized, project, tracker)


def build_delivery_payload(item: dict[str, Any], subscription: NotificationSubscription) -> dict[str, Any]:
    return {
        'subscription_id': subscription.id,
        'provider': subscription.provider,
        'destination': subscription.destination,
        'recipient_user_id': subscription.recipient_user_id,
        'config': _json_dict(subscription.config_json),
        'event': item,
    }


def enqueue_tracker_event_deliveries(db: Session, event: TrackerEvent) -> None:
    subscriptions = (
        db.query(NotificationSubscription)
        .filter(NotificationSubscription.is_enabled == True)  # noqa: E712
        .all()
    )
    if not subscriptions:
        return

    now = time.time()
    for subscription in subscriptions:
        if subscription.provider not in NOTIFICATION_PROVIDERS:
            continue
        if not _subscription_filters_match(subscription, event):
            continue
        recipient = _recipient_user(subscription.recipient_user_id)
        if recipient is None:
            continue
        if not _channel_enabled_for_user(db, recipient, subscription.provider, event.event_type):
            continue
        item = _event_visible_for_subscription(db, subscription=subscription, event=event, user=recipient)
        if item is None:
            continue
        existing = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.tracker_event_id == event.id)
            .filter(NotificationDelivery.subscription_id == subscription.id)
            .filter(NotificationDelivery.recipient_user_id == subscription.recipient_user_id)
            .first()
        )
        if existing is not None:
            continue
        db.add(NotificationDelivery(
            id=str(uuid.uuid4()),
            tracker_event_id=event.id,
            recipient_user_id=subscription.recipient_user_id,
            subscription_id=subscription.id,
            provider=subscription.provider,
            status='pending',
            attempts=0,
            next_attempt_at=now,
            payload_json=json.dumps(build_delivery_payload(item, subscription)),
            created_at=now,
            updated_at=now,
        ))


def serialize_subscription(subscription: NotificationSubscription) -> dict[str, Any]:
    recipient = _recipient_user(subscription.recipient_user_id) or {}
    return {
        'id': subscription.id,
        'provider': subscription.provider,
        'recipient_user_id': subscription.recipient_user_id,
        'recipient_display_name': recipient.get('display_name') or subscription.recipient_user_id,
        'destination': subscription.destination,
        'scope': subscription.scope,
        'project_filters': _json_list(subscription.project_filters_json),
        'event_filters': _json_list(subscription.event_filters_json),
        'config': _json_dict(subscription.config_json),
        'is_enabled': bool(subscription.is_enabled),
        'created_by': subscription.created_by,
        'created_at': subscription.created_at,
        'updated_at': subscription.updated_at,
    }


def create_subscription(db: Session, *, data: dict[str, Any], created_by: str | None) -> dict[str, Any]:
    provider = str(data.get('provider') or '').strip()
    if provider not in NOTIFICATION_PROVIDERS:
        raise HTTPException(status_code=400, detail='Invalid notification provider')
    recipient_user_id = str(data.get('recipient_user_id') or '').strip()
    if recipient_user_id not in load_users():
        raise HTTPException(status_code=400, detail='Recipient user not found')
    destination = _normalize_discord_channel_id(data.get('destination'))
    if not destination:
        raise HTTPException(status_code=400, detail='Destination must be a Discord channel ID')
    now = time.time()
    subscription = NotificationSubscription(
        id=str(uuid.uuid4()),
        provider=provider,
        recipient_user_id=recipient_user_id,
        destination=destination,
        scope=normalize_notification_scope(data.get('scope'), load_users().get(recipient_user_id)),
        project_filters_json=json.dumps(_normalize_event_types(data.get('project_filters'))),
        event_filters_json=json.dumps(_normalize_event_types(data.get('event_filters'))),
        config_json=json.dumps(data.get('config') if isinstance(data.get('config'), dict) else {}),
        is_enabled=bool(data.get('is_enabled', True)),
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return serialize_subscription(subscription)


def update_subscription(db: Session, subscription_id: str, data: dict[str, Any]) -> dict[str, Any]:
    subscription = db.query(NotificationSubscription).filter(NotificationSubscription.id == subscription_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail='Notification subscription not found')
    users = load_users()
    if 'provider' in data and data.get('provider') is not None:
        provider = str(data.get('provider') or '').strip()
        if provider not in NOTIFICATION_PROVIDERS:
            raise HTTPException(status_code=400, detail='Invalid notification provider')
        subscription.provider = provider
    if 'recipient_user_id' in data and data.get('recipient_user_id') is not None:
        recipient_user_id = str(data.get('recipient_user_id') or '').strip()
        if recipient_user_id not in users:
            raise HTTPException(status_code=400, detail='Recipient user not found')
        subscription.recipient_user_id = recipient_user_id
    if 'destination' in data and data.get('destination') is not None:
        destination = _normalize_discord_channel_id(data.get('destination'))
        if not destination:
            raise HTTPException(status_code=400, detail='Destination must be a Discord channel ID')
        subscription.destination = destination
    if 'scope' in data and data.get('scope') is not None:
        subscription.scope = normalize_notification_scope(data.get('scope'), users.get(subscription.recipient_user_id))
    if 'project_filters' in data and data.get('project_filters') is not None:
        subscription.project_filters_json = json.dumps(_normalize_event_types(data.get('project_filters')))
    if 'event_filters' in data and data.get('event_filters') is not None:
        subscription.event_filters_json = json.dumps(_normalize_event_types(data.get('event_filters')))
    if 'config' in data and data.get('config') is not None:
        subscription.config_json = json.dumps(data.get('config') or {})
    if 'is_enabled' in data and data.get('is_enabled') is not None:
        subscription.is_enabled = bool(data.get('is_enabled'))
    subscription.updated_at = time.time()
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return serialize_subscription(subscription)


def delete_subscription(db: Session, subscription_id: str) -> None:
    subscription = db.query(NotificationSubscription).filter(NotificationSubscription.id == subscription_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail='Notification subscription not found')
    db.query(NotificationDelivery).filter(NotificationDelivery.subscription_id == subscription_id).delete()
    db.delete(subscription)
    db.commit()


def serialize_delivery(delivery: NotificationDelivery) -> dict[str, Any]:
    return {
        'id': delivery.id,
        'tracker_event_id': delivery.tracker_event_id,
        'recipient_user_id': delivery.recipient_user_id,
        'subscription_id': delivery.subscription_id,
        'provider': delivery.provider,
        'status': delivery.status,
        'attempts': delivery.attempts,
        'next_attempt_at': delivery.next_attempt_at,
        'sent_at': delivery.sent_at,
        'last_error': 'Delivery failed' if delivery.last_error else None,
        'payload': _json_dict(delivery.payload_json),
        'created_at': delivery.created_at,
        'updated_at': delivery.updated_at,
    }


def _discord_field(name: str, value: Any, *, inline: bool = True) -> dict[str, Any] | None:
    text = str(value or '').strip()
    if not text:
        return None
    return {'name': name, 'value': text[:1024], 'inline': inline}


def _discord_event_color(event_type: str) -> int:
    if event_type in {'status_changed', 'status_changed_bulk'}:
        return 0x57D99A
    if event_type in {'comment_added', 'comment_resolved', 'comment_deleted'}:
        return 0x8BA7FF
    if event_type in {'version_added', 'versions_bulk_updated'}:
        return 0xF3C56B
    if event_type in {'shot_deleted', 'shots_deleted_bulk'}:
        return 0xF06A6A
    return 0x62E6B0


def _discord_message(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get('event') or {}
    event_payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
    config = payload.get('config') if isinstance(payload.get('config'), dict) else {}
    mention_everyone = bool(config.get('mention_everyone'))
    title = event.get('summary') or event.get('event_type') or 'Vueio activity'
    event_type = str(event.get('event_type') or 'activity')

    description_parts: list[str] = []
    old_label = event_payload.get('old_label') or event_payload.get('old_value')
    new_label = event_payload.get('new_label') or event_payload.get('new_value')
    if old_label or new_label:
        description_parts.append(f'`{old_label or "None"}` -> `{new_label or "None"}`')

    fields = [
        _discord_field('Project', event.get('project_title') or event.get('project_id')),
        _discord_field('Tracker', event.get('tracker_name')),
        _discord_field('Shot', event_payload.get('shot_code') or event.get('shot_id')),
        _discord_field('Actor', event.get('actor_name') or 'Unknown'),
        _discord_field('Type', event_type.replace('_', ' ')),
        _discord_field('Time', event.get('created_at_iso')),
    ]
    fields = [field for field in fields if field is not None]

    message: dict[str, Any] = {
        'content': '@everyone' if mention_everyone else '',
        'embeds': [{
            'title': title[:256],
            'description': '\n'.join(description_parts)[:4096] if description_parts else None,
            'color': _discord_event_color(event_type),
            'fields': fields[:25],
            'footer': {'text': 'Vueio notifications'},
        }],
        'allowed_mentions': {'parse': ['everyone'] if mention_everyone else []},
    }
    message['embeds'][0] = {key: value for key, value in message['embeds'][0].items() if value not in (None, '', [])}
    return message


def send_discord_payload(payload: dict[str, Any]) -> None:
    token = _discord_token()
    if not token:
        raise RuntimeError('DISCORD_BOT_TOKEN is not configured')
    destination = _normalize_discord_channel_id(payload.get('destination'))
    if not destination:
        raise RuntimeError('Discord channel id is missing or invalid')
    url = f'https://discord.com/api/v10/channels/{quote(destination, safe="")}/messages'
    with httpx.Client(timeout=10) as client:
        response = client.post(
            url,
            headers={'Authorization': f'Bot {token}', 'Content-Type': 'application/json'},
            json=_discord_message(payload),
        )
    if response.status_code >= 400:
        raise RuntimeError(f'Discord send failed with HTTP {response.status_code}')


def send_subscription_test(subscription: NotificationSubscription) -> None:
    payload = {
        'subscription_id': subscription.id,
        'provider': subscription.provider,
        'destination': subscription.destination,
        'recipient_user_id': subscription.recipient_user_id,
        'config': _json_dict(subscription.config_json),
        'event': {
            'summary': 'Vueio notification test',
            'event_type': 'test',
            'actor_name': 'Vueio',
            'project_title': 'System',
            'tracker_name': 'Notifications',
            'created_at_iso': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        },
    }
    _send_provider_payload(subscription.provider, payload)


def _send_provider_payload(provider: str, payload: dict[str, Any]) -> None:
    if provider == 'discord':
        send_discord_payload(payload)
        return
    raise RuntimeError(f'Notification provider is not implemented: {provider}')


def dispatch_due_notifications_once(limit: int = 25) -> int:
    db = SessionLocal()
    now = time.time()
    processed = 0
    try:
        deliveries = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.status.in_(['pending', 'failed']))
            .filter(or_(NotificationDelivery.next_attempt_at == None, NotificationDelivery.next_attempt_at <= now))  # noqa: E711
            .filter(NotificationDelivery.attempts < MAX_DELIVERY_ATTEMPTS)
            .order_by(NotificationDelivery.created_at.asc())
            .limit(limit)
            .all()
        )
        for delivery in deliveries:
            delivery.status = 'sending'
            delivery.attempts = int(delivery.attempts or 0) + 1
            delivery.updated_at = time.time()
            db.add(delivery)
            db.commit()
            try:
                _send_provider_payload(delivery.provider, _json_dict(delivery.payload_json))
                delivery.status = 'sent'
                delivery.sent_at = time.time()
                delivery.last_error = None
            except Exception as exc:
                delay = min(300, 2 ** min(delivery.attempts, 8))
                delivery.status = 'failed'
                delivery.last_error = 'Delivery failed'
                delivery.next_attempt_at = time.time() + delay
                logger.warning('Notification delivery failed (%s)', type(exc).__name__)
            delivery.updated_at = time.time()
            db.add(delivery)
            db.commit()
            processed += 1
        return processed
    finally:
        db.close()


def _dispatcher_loop() -> None:
    while True:
        try:
            dispatch_due_notifications_once()
        except Exception as exc:
            logger.warning('Notification dispatcher tick failed (%s)', type(exc).__name__)
        time.sleep(DISPATCH_INTERVAL_SECONDS)


def start_notification_dispatcher() -> None:
    global _dispatcher_started
    with _dispatcher_lock:
        if _dispatcher_started:
            return
        thread = threading.Thread(target=_dispatcher_loop, name='vueio-notification-dispatcher', daemon=True)
        thread.start()
        _dispatcher_started = True
