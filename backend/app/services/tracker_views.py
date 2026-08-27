from __future__ import annotations

import json
import re
import time
from ipaddress import ip_address
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.limiter import client_rate_limit_key
from app.models import HorizonShot, HorizonShotVersion, ShareLink, TrackerViewEvent
from app.services.horizons_fresh import (
    can_access_horizon_shot_version_id,
    get_horizon_shot_by_ref,
    require_horizon_shot_view_access,
)
from app.services.history_retention import prune_persistent_history


TRACKER_VIEW_PAGE_LIMIT_DEFAULT = 50
TRACKER_VIEW_PAGE_LIMIT_MAX = 100
TRACKER_VIEW_ACTIVE_SECONDS = 120
TRACKER_VIEW_ACTIVE_LIMIT = 200
TRACKER_VIEW_DEDUP_SECONDS = 10
TRACKER_VIEW_CLIENT_FIELDS = {
    'ip_address',
    'network',
    'browser',
    'operating_system',
    'language',
    'city',
    'region',
    'country',
    'timezone',
    'location_source',
}


class TrackerViewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    action: Literal['open', 'heartbeat', 'media']
    visit_id: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    shot_id: str | None = Field(default=None, max_length=160)
    version_id: str | None = Field(default=None, max_length=160)
    media_context: Literal['version', 'brief'] = 'version'


def classify_tracker_view_device(request: Request) -> str:
    """Reduce the user agent to a coarse device class."""
    user_agent = str(request.headers.get('user-agent') or '').lower()
    if 'ipad' in user_agent or ('macintosh' in user_agent and 'mobile' in user_agent):
        return 'tablet'
    if 'tablet' in user_agent or ('android' in user_agent and 'mobile' not in user_agent):
        return 'tablet'
    if any(marker in user_agent for marker in ('mobile', 'iphone', 'ipod', 'android')):
        return 'mobile'
    return 'desktop'


def _header_text(request: Request, name: str, *, max_length: int = 120) -> str:
    value = ' '.join(str(request.headers.get(name) or '').split())
    return value[:max_length]


def _major_version(value: str) -> str:
    return str(value or '').split('.', 1)[0]


def _browser_label(request: Request) -> str:
    client_hints = _header_text(request, 'sec-ch-ua', max_length=320)
    for label, pattern in (
        ('Edge', r'"Microsoft Edge";v="(\d+)"'),
        ('Chrome', r'"Google Chrome";v="(\d+)"'),
        ('Opera', r'"Opera";v="(\d+)"'),
        ('Chromium', r'"Chromium";v="(\d+)"'),
    ):
        match = re.search(pattern, client_hints, re.IGNORECASE)
        if match:
            return f'{label} {match.group(1)}'

    user_agent = _header_text(request, 'user-agent', max_length=640)
    for label, pattern in (
        ('Samsung Internet', r'SamsungBrowser/([\d.]+)'),
        ('Edge', r'(?:Edg|EdgiOS|EdgA)/([\d.]+)'),
        ('Opera', r'(?:OPR|Opera)/([\d.]+)'),
        ('Chrome', r'(?:Chrome|CriOS)/([\d.]+)'),
        ('Firefox', r'(?:Firefox|FxiOS)/([\d.]+)'),
        ('Safari', r'Version/([\d.]+).*Safari/'),
    ):
        match = re.search(pattern, user_agent, re.IGNORECASE)
        if match:
            return f'{label} {_major_version(match.group(1))}'
    return ''


def _operating_system_label(request: Request) -> str:
    user_agent = _header_text(request, 'user-agent', max_length=640)
    for label, pattern in (
        ('iOS', r'(?:CPU (?:iPhone )?OS|iPhone OS) ([\d_]+)'),
        ('Android', r'Android ([\d.]+)'),
        ('macOS', r'Mac OS X ([\d_]+)'),
    ):
        match = re.search(pattern, user_agent, re.IGNORECASE)
        if match:
            return f'{label} {_major_version(match.group(1).replace("_", "."))}'

    windows = re.search(r'Windows NT ([\d.]+)', user_agent, re.IGNORECASE)
    if windows:
        return {
            '10.0': 'Windows 10/11',
            '6.3': 'Windows 8.1',
            '6.2': 'Windows 8',
            '6.1': 'Windows 7',
        }.get(windows.group(1), 'Windows')
    if 'CrOS' in user_agent:
        return 'ChromeOS'
    if 'Linux' in user_agent:
        return 'Linux'

    platform = _header_text(request, 'sec-ch-ua-platform', max_length=40).strip('"')
    return platform


def _trusted_cloudflare_location(request: Request) -> bool:
    settings = get_settings()
    try:
        direct_address = ip_address(str(request.client.host if request.client else ''))
    except ValueError:
        return False
    return bool(
        settings.VUEIO_TRUST_PROXY_HEADERS
        and settings.VUEIO_TRUST_CLOUDFLARE
        and (direct_address.is_private or direct_address.is_loopback)
    )


def tracker_view_client_metadata(request: Request) -> dict[str, str]:
    metadata: dict[str, str] = {}
    address = client_rate_limit_key(request)
    try:
        parsed_address = ip_address(address)
    except ValueError:
        parsed_address = None
    if parsed_address is not None:
        metadata['ip_address'] = str(parsed_address)
        metadata['network'] = (
            'Local network'
            if parsed_address.is_private or parsed_address.is_loopback or parsed_address.is_link_local
            else 'Public internet'
        )

    browser = _browser_label(request)
    operating_system = _operating_system_label(request)
    language = _header_text(request, 'accept-language', max_length=80).partition(',')[0]
    if browser:
        metadata['browser'] = browser
    if operating_system:
        metadata['operating_system'] = operating_system
    if re.fullmatch(r'[A-Za-z0-9-]{2,35}', language):
        metadata['language'] = language

    if _trusted_cloudflare_location(request):
        for key, header, max_length in (
            ('city', 'cf-ipcity', 100),
            ('region', 'cf-region', 100),
            ('country', 'cf-ipcountry', 2),
            ('timezone', 'cf-timezone', 100),
        ):
            value = _header_text(request, header, max_length=max_length)
            if value:
                metadata[key] = value.upper() if key == 'country' else value
        if any(key in metadata for key in ('city', 'region', 'country', 'timezone')):
            metadata['location_source'] = 'Cloudflare IP location'
    return metadata


def _client_metadata_json(request: Request) -> str | None:
    metadata = tracker_view_client_metadata(request)
    return json.dumps(metadata, ensure_ascii=False, separators=(',', ':'), sort_keys=True) if metadata else None


def _read_client_metadata(raw: str | None) -> dict[str, str]:
    try:
        payload = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: str(payload[key])[:160]
        for key in TRACKER_VIEW_CLIENT_FIELDS
        if isinstance(payload.get(key), str) and payload[key].strip()
    }


def _viewer_user_id(user: dict | None) -> str | None:
    if not user:
        return None
    return str(user.get('id') or user.get('username') or '').strip() or None


def _viewer_name(user: dict | None, source: str) -> str:
    if source == 'share':
        return 'Shared viewer'
    if not user:
        return 'Viewer'
    return str(
        user.get('display_name')
        or user.get('name')
        or user.get('username')
        or user.get('id')
        or 'Viewer'
    ).strip()[:120]


def _visit_query(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    visit_id: str,
    user: dict | None,
    source: str,
    share: ShareLink | None,
):
    query = (
        db.query(TrackerViewEvent)
        .filter(TrackerViewEvent.project_id == project_id)
        .filter(TrackerViewEvent.tracker_id == tracker_id)
        .filter(TrackerViewEvent.visit_id == visit_id)
    )
    if source == 'share':
        return query.filter(TrackerViewEvent.source == 'share').filter(
            TrackerViewEvent.share_id == (share.id if share else None)
        )
    return query.filter(TrackerViewEvent.source == 'app').filter(
        TrackerViewEvent.viewer_user_id == _viewer_user_id(user)
    )


def _ensure_tracker_open_event(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    visit_id: str,
    user: dict | None,
    source: str,
    share: ShareLink | None,
    request: Request,
    device_type: str,
    now: float,
) -> tuple[TrackerViewEvent, bool]:
    existing = (
        _visit_query(
            db,
            project_id=project_id,
            tracker_id=tracker_id,
            visit_id=visit_id,
            user=user,
            source=source,
            share=share,
        )
        .filter(TrackerViewEvent.event_type == 'tracker_opened')
        .first()
    )
    if existing:
        existing.last_seen_at = now
        existing.device_type = device_type
        if not existing.client_metadata_json:
            existing.client_metadata_json = _client_metadata_json(request)
        db.add(existing)
        return existing, False

    event = TrackerViewEvent(
        project_id=project_id,
        tracker_id=tracker_id,
        visit_id=visit_id,
        viewer_user_id=_viewer_user_id(user) if source == 'app' else None,
        viewer_name=_viewer_name(user, source),
        source=source,
        share_id=share.id if share else None,
        event_type='tracker_opened',
        device_type=device_type,
        client_metadata_json=_client_metadata_json(request),
        created_at=now,
        last_seen_at=now,
    )
    db.add(event)
    db.flush()
    return event, True


def _resolve_viewed_media(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    data: TrackerViewRequest,
    user: dict | None,
    access_role: str | None,
    allowed_shot_ids: set[str] | None,
    allowed_version_ids: set[str] | None,
) -> tuple[HorizonShot, HorizonShotVersion | None]:
    if not data.shot_id:
        raise HTTPException(status_code=400, detail='A shot is required for media viewing activity')

    if allowed_shot_ids is None:
        shot = require_horizon_shot_view_access(
            db,
            project_id,
            data.shot_id,
            tracker_id=tracker_id,
            user=user,
            access_role=access_role,
        )
    else:
        shot = get_horizon_shot_by_ref(db, project_id, data.shot_id, tracker_id=tracker_id)
        if shot.id not in allowed_shot_ids:
            raise HTTPException(status_code=404, detail='Shot not found')

    if data.media_context == 'brief':
        return shot, None
    if not data.version_id:
        raise HTTPException(status_code=400, detail='A version is required for version viewing activity')

    version = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.id == data.version_id)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.tracker_id == tracker_id)
        .filter(HorizonShotVersion.shot_id == shot.id)
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail='Version not found')
    if allowed_version_ids is not None and version.id not in allowed_version_ids:
        raise HTTPException(status_code=404, detail='Version not found')
    if allowed_version_ids is None and not can_access_horizon_shot_version_id(
        db,
        project_id,
        version.id,
        user=user,
        access_role=access_role,
    ):
        raise HTTPException(status_code=404, detail='Version not found')
    return shot, version


def record_tracker_view(
    db: Session,
    *,
    request: Request,
    project_id: str,
    tracker_id: str,
    data: TrackerViewRequest,
    user: dict | None = None,
    access_role: str | None = None,
    source: str = 'app',
    share: ShareLink | None = None,
    allowed_shot_ids: set[str] | None = None,
    allowed_version_ids: set[str] | None = None,
) -> dict:
    now = time.time()
    device_type = classify_tracker_view_device(request)
    session_event, session_created = _ensure_tracker_open_event(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
        visit_id=data.visit_id,
        user=user,
        source=source,
        share=share,
        request=request,
        device_type=device_type,
        now=now,
    )
    new_event_ids = [session_event.id] if session_created and session_event.id else []

    if data.action == 'media':
        shot, version = _resolve_viewed_media(
            db,
            project_id=project_id,
            tracker_id=tracker_id,
            data=data,
            user=user,
            access_role=access_role,
            allowed_shot_ids=allowed_shot_ids,
            allowed_version_ids=allowed_version_ids,
        )
        existing = (
            _visit_query(
                db,
                project_id=project_id,
                tracker_id=tracker_id,
                visit_id=data.visit_id,
                user=user,
                source=source,
                share=share,
            )
            .filter(TrackerViewEvent.event_type == 'media_viewed')
            .filter(TrackerViewEvent.shot_id == shot.id)
            .filter(
                TrackerViewEvent.shot_version_id == version.id
                if version is not None
                else TrackerViewEvent.shot_version_id.is_(None)
            )
            .filter(TrackerViewEvent.created_at >= now - TRACKER_VIEW_DEDUP_SECONDS)
            .order_by(TrackerViewEvent.created_at.desc())
            .first()
        )
        if existing:
            existing.last_seen_at = now
            if not existing.client_metadata_json:
                existing.client_metadata_json = session_event.client_metadata_json
            db.add(existing)
            media_event = existing
        else:
            media_event = TrackerViewEvent(
                project_id=project_id,
                tracker_id=tracker_id,
                shot_id=shot.id,
                shot_version_id=version.id if version else None,
                visit_id=data.visit_id,
                viewer_user_id=_viewer_user_id(user) if source == 'app' else None,
                viewer_name=_viewer_name(user, source),
                source=source,
                share_id=share.id if share else None,
                event_type='media_viewed',
                device_type=device_type,
                client_metadata_json=session_event.client_metadata_json,
                created_at=now,
                last_seen_at=now,
            )
            db.add(media_event)
            db.flush()
            if media_event.id:
                new_event_ids.append(media_event.id)

        session_event.shot_id = shot.id
        session_event.shot_version_id = version.id if version else None
        session_event.last_seen_at = now
        db.add(session_event)
    else:
        media_event = None

    if any(event_id % 100 == 0 for event_id in new_event_ids):
        prune_persistent_history(db, now=now)
    db.commit()
    return {
        'status': 'ok',
        'visit_id': data.visit_id,
        'last_seen_at': now,
    }


def _view_maps(db: Session, rows: list[TrackerViewEvent]) -> tuple[dict[str, HorizonShot], dict[str, HorizonShotVersion]]:
    shot_ids = {row.shot_id for row in rows if row.shot_id}
    version_ids = {row.shot_version_id for row in rows if row.shot_version_id}
    shots = {
        shot.id: shot
        for shot in db.query(HorizonShot).filter(HorizonShot.id.in_(shot_ids)).all()
    } if shot_ids else {}
    versions = {
        version.id: version
        for version in db.query(HorizonShotVersion).filter(HorizonShotVersion.id.in_(version_ids)).all()
    } if version_ids else {}
    return shots, versions


def _serialize_tracker_view(
    row: TrackerViewEvent,
    *,
    shots: dict[str, HorizonShot],
    versions: dict[str, HorizonShotVersion],
    active: bool = False,
) -> dict:
    shot = shots.get(row.shot_id or '')
    version = versions.get(row.shot_version_id or '')
    version_label = _view_version_label(version)
    if active:
        summary = (
            f'Viewing {shot.shot_code}, {version_label}'
            if shot and version_label
            else f'Viewing {shot.shot_code} brief'
            if shot
            else 'Browsing tracker'
        )
    elif row.event_type == 'tracker_opened':
        summary = 'Opened tracker'
    else:
        summary = (
            f'Viewed {shot.shot_code}, {version_label}'
            if shot and version_label
            else f'Viewed {shot.shot_code} brief'
            if shot
            else 'Viewed tracker media'
        )
    return {
        'id': row.id,
        'event_type': row.event_type,
        'viewer_user_id': row.viewer_user_id,
        'viewer_name': row.viewer_name,
        'source': row.source,
        'share_id': row.share_id,
        'visit_id': row.visit_id,
        'device_type': row.device_type,
        'client': _read_client_metadata(row.client_metadata_json),
        'created_at': row.created_at,
        'last_seen_at': row.last_seen_at,
        'shot_id': row.shot_id,
        'shot_code': shot.shot_code if shot else None,
        'shot_version_id': row.shot_version_id,
        'version_label': version_label,
        'summary': summary,
    }


def _view_version_label(version: HorizonShotVersion | None) -> str | None:
    if version is None:
        return None
    label = str(version.label or '').strip()
    if not label:
        return 'Version'
    if label.lower().startswith('v'):
        return f'V{label[1:]}'
    if label.isdigit():
        return f'V{label}'
    return label


def list_tracker_views(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    limit: int | None = None,
    before: float | None = None,
    now: float | None = None,
) -> dict:
    current_time = time.time() if now is None else now
    page_limit = max(1, min(int(limit or TRACKER_VIEW_PAGE_LIMIT_DEFAULT), TRACKER_VIEW_PAGE_LIMIT_MAX))
    query = (
        db.query(TrackerViewEvent)
        .filter(TrackerViewEvent.project_id == project_id)
        .filter(TrackerViewEvent.tracker_id == tracker_id)
    )
    if before is not None:
        query = query.filter(TrackerViewEvent.created_at < before)
    rows = (
        query
        .order_by(TrackerViewEvent.created_at.desc(), TrackerViewEvent.id.desc())
        .limit(page_limit + 1)
        .all()
    )
    has_more = len(rows) > page_limit
    rows = rows[:page_limit]

    active_rows = (
        db.query(TrackerViewEvent)
        .filter(TrackerViewEvent.project_id == project_id)
        .filter(TrackerViewEvent.tracker_id == tracker_id)
        .filter(TrackerViewEvent.event_type == 'tracker_opened')
        .filter(TrackerViewEvent.last_seen_at >= current_time - TRACKER_VIEW_ACTIVE_SECONDS)
        .order_by(TrackerViewEvent.last_seen_at.desc(), TrackerViewEvent.id.desc())
        .limit(TRACKER_VIEW_ACTIVE_LIMIT)
        .all()
    )
    shots, versions = _view_maps(db, [*rows, *active_rows])
    return {
        'active': [
            _serialize_tracker_view(row, shots=shots, versions=versions, active=True)
            for row in active_rows
        ],
        'items': [
            _serialize_tracker_view(row, shots=shots, versions=versions)
            for row in rows
        ],
        'next_before': rows[-1].created_at if has_more and rows else None,
    }
