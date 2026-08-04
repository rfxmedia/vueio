from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import DownloadEvent
from app.services.history_retention import prune_persistent_history


DOWNLOAD_EVENT_LIMIT_DEFAULT = 100
DOWNLOAD_EVENT_LIMIT_MAX = 500
DOWNLOAD_METADATA_FIELDS = {
    'access_role',
    'file_count',
    'job_status',
    'progress',
    'selected_shots',
}


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, separators=(',', ':'), default=str)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _actor_from_user(user: dict[str, Any] | None, *, fallback_name: str = 'Shared viewer') -> dict[str, str | None]:
    if user:
        return {
            'user_id': user.get('id') or user.get('username'),
            'user_name': user.get('display_name') or user.get('name') or user.get('username') or user.get('id') or 'Unknown',
        }
    return {'user_id': None, 'user_name': fallback_name}


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in (metadata or {}).items()
        if key in DOWNLOAD_METADATA_FIELDS and isinstance(value, (bool, float, int, str))
    }


def create_download_event(
    db: Session,
    *,
    request: Request | None = None,
    user: dict[str, Any] | None = None,
    source: str = 'app',
    auth_mode: str | None = None,
    share_id: str | None = None,
    project_id: str | None = None,
    tracker_id: str | None = None,
    event_type: str = 'download',
    resource_type: str = 'file',
    resource_id: str | None = None,
    resource_name: str | None = None,
    filename: str | None = None,
    paths: list[str] | None = None,
    size_bytes: int | None = None,
    status: str = 'started',
    metadata: dict[str, Any] | None = None,
    create_tracker_activity: bool = False,
) -> DownloadEvent:
    # The request and selected paths are intentionally not persisted. Download
    # history identifies the actor and resource without fingerprinting clients
    # or retaining filesystem details.
    _ = request, paths
    now = time.time()
    actor = _actor_from_user(user)
    safe_metadata = _safe_metadata(metadata)
    event = DownloadEvent(
        id=uuid.uuid4().hex,
        created_at=now,
        user_id=actor['user_id'],
        user_name=actor['user_name'],
        source=source,
        auth_mode=auth_mode,
        share_id=share_id,
        project_id=project_id,
        tracker_id=tracker_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        filename=filename,
        paths_json='[]',
        size_bytes=size_bytes,
        status=status,
        ip_address=None,
        ip_chain_json='{}',
        geo_json='{}',
        device_json='{}',
        request_json='{}',
        client_json='{}',
        metadata_json=_json_dumps(safe_metadata),
    )
    db.add(event)
    db.flush()

    if create_tracker_activity and project_id and tracker_id:
        try:
            from app.services.tracker_events import create_tracker_event
            create_tracker_event(
                db,
                project_id=project_id,
                tracker_id=tracker_id,
                event_type='download_started',
                actor_id=event.user_id,
                actor_name=event.user_name or 'Unknown',
                source=source,
                payload={
                    'download_event_id': event.id,
                    'download_type': event_type,
                    'resource_type': resource_type,
                    'resource_name': resource_name,
                    'filename': filename,
                    'share_id': share_id,
                    'paths_count': len(paths or []),
                    **safe_metadata,
                },
            )
        except Exception:
            pass

    prune_persistent_history(db, now=now)
    db.commit()
    db.refresh(event)
    return event


def serialize_download_event(event: DownloadEvent) -> dict[str, Any]:
    return {
        'id': event.id,
        'created_at': event.created_at,
        'user_id': event.user_id,
        'user_name': event.user_name,
        'source': event.source,
        'auth_mode': event.auth_mode,
        'share_id': event.share_id,
        'project_id': event.project_id,
        'tracker_id': event.tracker_id,
        'event_type': event.event_type,
        'resource_type': event.resource_type,
        'resource_id': event.resource_id,
        'resource_name': event.resource_name,
        'filename': event.filename,
        'paths': [],
        'size_bytes': event.size_bytes,
        'status': event.status,
        'metadata': _json_loads(event.metadata_json, {}),
    }


def list_download_events(
    db: Session,
    *,
    limit: int | None = None,
    project_id: str | None = None,
    share_id: str | None = None,
) -> dict[str, Any]:
    page_limit = max(1, min(int(limit or DOWNLOAD_EVENT_LIMIT_DEFAULT), DOWNLOAD_EVENT_LIMIT_MAX))
    query = db.query(DownloadEvent)
    if project_id:
        query = query.filter(DownloadEvent.project_id == project_id)
    if share_id:
        query = query.filter(DownloadEvent.share_id == share_id)
    rows = query.order_by(DownloadEvent.created_at.desc()).limit(page_limit).all()
    return {'events': [serialize_download_event(row) for row in rows]}
