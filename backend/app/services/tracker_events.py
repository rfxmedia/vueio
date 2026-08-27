from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Comment, HorizonProject, HorizonShot, HorizonShotVersion, HorizonTracker, TrackerEvent


TRACKER_EVENT_PAGE_LIMIT_DEFAULT = 40
TRACKER_EVENT_PAGE_LIMIT_MAX = 100
logger = logging.getLogger('vueio.tracker_events')


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def _json_payload(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def create_tracker_event(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    event_type: str,
    actor_name: str,
    source: str,
    actor_id: str | None = None,
    shot_id: str | None = None,
    shot_version_id: str | None = None,
    comment_id: str | int | None = None,
    payload: dict[str, Any] | None = None,
    created_at: float | None = None,
) -> TrackerEvent:
    from app.services.tracker_history import TRACKER_STATE_EVENT_TYPES, lock_tracker_for_history

    if event_type in TRACKER_STATE_EVENT_TYPES:
        # All restorable mutations share this row lock with full History
        # restores, giving snapshots one unambiguous order under concurrency.
        lock_tracker_for_history(db, project_id=project_id, tracker_id=tracker_id)
    event = TrackerEvent(
        project_id=project_id,
        tracker_id=tracker_id,
        shot_id=shot_id,
        shot_version_id=shot_version_id,
        comment_id=str(comment_id) if comment_id is not None else None,
        event_type=event_type,
        actor_id=actor_id,
        actor_name=actor_name,
        source=source,
        payload_json=json.dumps(_normalize_payload(payload)),
        created_at=created_at or time.time(),
    )
    db.add(event)
    db.flush()
    from app.services.tracker_history import capture_tracker_event_state
    capture_tracker_event_state(db, event)
    try:
        from app.services.notifications import enqueue_tracker_event_deliveries
        enqueue_tracker_event_deliveries(db, event)
    except Exception as exc:
        # Activity creation must not fail because an external delivery route is misconfigured.
        logger.warning('Failed to enqueue notification deliveries (%s)', type(exc).__name__)
    if event.id and event.id % 100 == 0:
        from app.services.history_retention import prune_persistent_history
        prune_persistent_history(db)
    return event


def build_tracker_event_actor(
    *,
    user: dict | None = None,
    source: str = 'app',
    actor_name: str | None = None,
    actor_id: str | None = None,
) -> dict[str, str | None]:
    resolved_name = (actor_name or '').strip()
    resolved_id = (actor_id or '').strip() or None

    if user:
        return {
            'actor_id': resolved_id or user.get('id') or user.get('username'),
            'actor_name': resolved_name or user.get('display_name') or user.get('name') or user.get('username') or user.get('id') or 'Unknown',
            'source': source,
        }

    if source == 'share':
        return {
            'actor_id': resolved_id,
            'actor_name': resolved_name or 'Shared reviewer',
            'source': 'share',
        }

    return {
        'actor_id': resolved_id,
        'actor_name': resolved_name or 'Unknown',
        'source': source,
    }


def get_tracker_event_context_for_version(
    db: Session,
    *,
    project_id: str,
    shot_version_id: str | None = None,
    media_asset_id: str | None = None,
) -> dict[str, str] | None:
    version = None
    if shot_version_id:
        version = (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.id == shot_version_id)
            .first()
        )
    elif media_asset_id:
        versions = (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.media_asset_id == media_asset_id)
            .order_by(HorizonShotVersion.updated_at.desc(), HorizonShotVersion.created_at.desc(), HorizonShotVersion.id.asc())
            .limit(2)
            .all()
        )
        version = versions[0] if len(versions) == 1 else None
    if version is None:
        return None

    shot = (
        db.query(HorizonShot)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShot.id == version.shot_id)
        .first()
    )
    if shot is None:
        return None

    tracker = (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == project_id)
        .filter(HorizonTracker.id == shot.tracker_id)
        .first()
    )
    if tracker is None:
        return None

    return {
        'tracker_id': tracker.id,
        'tracker_name': tracker.name,
        'shot_id': shot.id,
        'shot_code': shot.shot_code,
        'shot_version_id': version.id,
        'version_label': version.label,
    }


def lock_tracker_for_comment_target(
    db: Session,
    *,
    project_id: str | None,
    shot_version_id: str | None = None,
    media_asset_id: str | None = None,
) -> dict[str, str] | None:
    if not project_id:
        return None
    context = get_tracker_event_context_for_version(
        db,
        project_id=project_id,
        shot_version_id=shot_version_id,
        media_asset_id=media_asset_id,
    )
    if context is not None:
        from app.services.tracker_history import prepare_tracker_history_mutation

        prepare_tracker_history_mutation(
            db,
            project_id=project_id,
            tracker_id=context['tracker_id'],
        )
    return context


def _event_shots_for_visibility(
    payload: dict[str, Any],
    visible_shot_ids: set[str] | None,
    visible_version_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    shots = payload.get('shots')
    if not isinstance(shots, list):
        return []
    visible = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get('id') or shot.get('shot_id') or '').strip()
        version_id = str(shot.get('version_id') or shot.get('shot_version_id') or '').strip()
        if visible_shot_ids is not None and shot_id not in visible_shot_ids:
            continue
        if visible_version_ids is not None and version_id and version_id not in visible_version_ids:
            continue
        visible.append(shot)
    return visible


def _event_visible(
    event: TrackerEvent,
    payload: dict[str, Any],
    visible_shot_ids: set[str] | None,
    visible_version_ids: set[str] | None,
) -> bool:
    version_ref = str(
        event.shot_version_id
        or payload.get('shot_version_id')
        or payload.get('version_id')
        or ''
    ).strip()
    if visible_version_ids is not None and version_ref and version_ref not in visible_version_ids:
        return False
    if visible_shot_ids is None:
        return True
    if event.shot_id:
        return event.shot_id in visible_shot_ids
    shots = _event_shots_for_visibility(payload, visible_shot_ids, visible_version_ids)
    if 'shots' in payload:
        return bool(shots)
    return False


def _summary_for_event(event_type: str, payload: dict[str, Any]) -> str:
    shot_code = payload.get('shot_code') or 'Shot'
    version_label = payload.get('version_label')
    tag = payload.get('new_value') if event_type == 'category_changed' else payload.get('tag') or payload.get('category')
    assignee_name = payload.get('assignee_name') or payload.get('new_value')

    if event_type == 'tracker_checkpoint':
        if payload.get('reason') == 'before_restore':
            return 'Saved tracker before restore'
        return 'Saved initial tracker state'
    if event_type == 'shot_created':
        return f'Created {shot_code}'
    if event_type == 'shot_deleted':
        return f'Deleted {shot_code}'
    if event_type == 'shot_archived':
        return f'Archived {shot_code}'
    if event_type == 'shot_restored':
        return f'Restored {shot_code}'
    if event_type == 'shot_reordered':
        return f'Reordered {payload.get("count", 0)} shots'
    if event_type == 'shot_renamed':
        return f'Renamed {payload.get("old_value")} to {payload.get("new_value")}'
    if event_type == 'brief_changed':
        return f'Updated brief for {shot_code}'
    if event_type == 'status_changed':
        return f'Changed {shot_code} status to {payload.get("new_label") or payload.get("new_value")}'
    if event_type == 'category_changed':
        if tag:
            return f'Changed {shot_code} tag to {tag}'
        return f'Cleared tag on {shot_code}'
    if event_type == 'assignee_changed':
        assignees = payload.get('assignees')
        if isinstance(assignees, list) and len(assignees) > 1:
            names = [
                item.get('display_name') or item.get('username') or item.get('id')
                for item in assignees
                if isinstance(item, dict)
            ]
            if names:
                return f'Assigned {shot_code} to {", ".join(names[:2])}{f" +{len(names) - 2}" if len(names) > 2 else ""}'
        if assignee_name:
            return f'Assigned {shot_code} to {assignee_name}'
        return f'Cleared assignee on {shot_code}'
    if event_type == 'version_added':
        suffix = f' ({version_label})' if version_label else ''
        return f'Added version to {shot_code}{suffix}'
    if event_type == 'version_published':
        suffix = f' {version_label}' if version_label else ''
        return f'Published{suffix} for {shot_code}'
    if event_type == 'version_kept_internal':
        suffix = f' {version_label}' if version_label else ''
        return f'Kept{suffix} internal for {shot_code}'
    if event_type == 'version_removed_from_shares':
        suffix = f' {version_label}' if version_label else ''
        return f'Removed{suffix} from shares for {shot_code}'
    if event_type == 'brief_file_uploaded':
        return f'Uploaded brief attachment for {shot_code}'
    if event_type == 'shots_imported':
        return f'Imported {payload.get("count", 0)} shots'
    if event_type == 'versions_bulk_updated':
        return f'Bulk updated {payload.get("count", 0)} shot versions'
    if event_type == 'status_changed_bulk':
        return f'Changed status on {payload.get("count", 0)} shots to {payload.get("new_label") or payload.get("new_value")}'
    if event_type == 'shots_bulk_updated':
        if payload.get('archive_action') in {'archived', 'restored'}:
            action = 'Archived' if payload.get('archive_action') == 'archived' else 'Restored'
            return f'{action} {payload.get("count", 0)} shots'
        fields = payload.get('fields') if isinstance(payload.get('fields'), list) else []
        field_label = ', '.join(str(field).replace('_', ' ') for field in fields) if fields else 'shot fields'
        return f'Updated {field_label} on {payload.get("count", 0)} shots'
    if event_type == 'shots_deleted_bulk':
        return f'Deleted {payload.get("count", 0)} shots'
    if event_type == 'comment_added':
        return f'Added comment on {shot_code}'
    if event_type == 'comment_resolved':
        return f'Resolved comment on {shot_code}'
    if event_type == 'comment_deleted':
        return f'Deleted comment on {shot_code}'
    if event_type == 'download_started':
        resource = payload.get('resource_name') or payload.get('filename') or 'tracker files'
        return f'Downloaded {resource}'
    if event_type == 'tracker_updated':
        return 'Updated tracker settings'
    if event_type == 'tracker_restored':
        target = payload.get('restored_to_summary') or 'an earlier point'
        return f'Restored tracker to {target}'
    if event_type == 'versions_updated':
        return f'Updated versions for {shot_code}'
    return event_type.replace('_', ' ')


def _navigation_target_for_event(event: TrackerEvent, payload: dict[str, Any]) -> dict[str, Any]:
    target: dict[str, Any] = {
        'type': 'tracker',
        'project_id': event.project_id,
        'tracker_id': event.tracker_id,
    }

    tracker_only_event = event.event_type in {'shot_deleted', 'shots_deleted_bulk', 'shot_archived'}
    if event.shot_id and not tracker_only_event:
        target.update({
            'type': 'shot',
            'shot_id': event.shot_id,
            'shot_code': payload.get('shot_code'),
            'mode': 'brief' if event.event_type in {'brief_changed', 'brief_file_uploaded'} else 'latest',
        })

    if event.shot_version_id and not tracker_only_event:
        target.update({
            'type': 'version',
            'shot_version_id': event.shot_version_id,
            'mode': 'brief' if event.event_type in {'brief_changed', 'brief_file_uploaded'} else 'latest',
        })

    if event.comment_id and not tracker_only_event:
        target.update({
            'type': 'comment',
            'comment_id': event.comment_id,
            'mode': 'latest',
        })

    shots = payload.get('shots')
    if not event.shot_id and isinstance(shots, list) and len(shots) == 1 and not tracker_only_event:
        shot = shots[0] if isinstance(shots[0], dict) else {}
        shot_id = shot.get('shot_id') or shot.get('id')
        if shot_id:
            target.update({
                'type': 'shot',
                'shot_id': shot_id,
                'shot_code': shot.get('shot_code'),
                'mode': 'latest',
            })

    return target


def _safe_activity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the small, presentation-only subset safe outside the owning team."""
    safe: dict[str, Any] = {}
    for key in ('shot_code', 'version_label', 'count'):
        value = payload.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            safe[key] = value

    shots = payload.get('shots')
    if isinstance(shots, list):
        safe_shots = []
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            safe_shot = {
                key: shot.get(key)
                for key in ('shot_code', 'version_label')
                if isinstance(shot.get(key), str)
            }
            if safe_shot:
                safe_shots.append(safe_shot)
        safe['shots'] = safe_shots
        safe['count'] = len(safe_shots)
    return safe


def _safe_activity_summary(event_type: str, payload: dict[str, Any], summary: str) -> str:
    shot_code = payload.get('shot_code') or 'shot'
    if event_type == 'assignee_changed':
        return f'Updated assignments on {shot_code}'
    if event_type == 'shot_renamed':
        return f'Renamed {shot_code}'
    if event_type == 'download_started':
        return 'Downloaded tracker files'
    return summary


def serialize_tracker_event(
    event: TrackerEvent,
    *,
    visible_shot_ids: set[str] | None = None,
    visible_version_ids: set[str] | None = None,
    audience: str = 'internal',
    restoreable: bool = False,
    current_point: bool = False,
    recovery_unavailable_reason: str | None = None,
) -> dict[str, Any] | None:
    payload = _json_payload(event.payload_json)
    payload.pop('_history_comment_id', None)
    if not _event_visible(event, payload, visible_shot_ids, visible_version_ids):
        return None

    if 'shots' in payload:
        payload['shots'] = _event_shots_for_visibility(payload, visible_shot_ids, visible_version_ids)
        payload['count'] = len(payload['shots'])

    summary = _summary_for_event(event.event_type, payload)
    target = _navigation_target_for_event(event, payload)
    is_safe_audience = audience in {'public', 'restricted'}
    if is_safe_audience:
        summary = _safe_activity_summary(event.event_type, payload, summary)
    serialized = {
        'id': event.id,
        'project_id': event.project_id,
        'tracker_id': event.tracker_id,
        'shot_id': event.shot_id,
        'shot_version_id': event.shot_version_id,
        'comment_id': event.comment_id,
        'event_type': event.event_type,
        'actor_id': event.actor_id,
        'actor_name': event.actor_name,
        'source': event.source,
        'restoreable': bool(restoreable),
        'current_point': bool(current_point),
        'created_at': event.created_at,
        'payload': _safe_activity_payload(payload) if is_safe_audience else payload,
        'summary': summary,
        'target': target,
    }
    if audience == 'internal' and recovery_unavailable_reason:
        serialized['recovery_unavailable'] = True
        serialized['recovery_unavailable_reason'] = recovery_unavailable_reason
    if audience == 'public':
        serialized.update({
            'actor_id': None,
            'actor_name': 'Shared reviewer' if event.source == 'share' else 'Team member',
            'restoreable': False,
            'current_point': False,
        })
    elif audience == 'restricted':
        serialized['actor_id'] = None
        serialized['restoreable'] = False
        serialized['current_point'] = False
    return serialized


def list_tracker_activity(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    limit: int | None = None,
    before: float | None = None,
    before_id: int | None = None,
    visible_shot_ids: set[str] | None = None,
    visible_version_ids: set[str] | None = None,
    audience: str = 'internal',
) -> dict[str, Any]:
    page_limit = max(1, min(int(limit or TRACKER_EVENT_PAGE_LIMIT_DEFAULT), TRACKER_EVENT_PAGE_LIMIT_MAX))
    items = []
    cursor = before
    cursor_id = before_id
    next_before = None
    next_before_id = None
    current_state_event_id = None
    if audience == 'internal':
        from app.services.tracker_history import TRACKER_STATE_EVENT_TYPES

        current_state_event_id = (
            db.query(TrackerEvent.id)
            .filter(TrackerEvent.project_id == project_id)
            .filter(TrackerEvent.tracker_id == tracker_id)
            .filter(TrackerEvent.event_type.in_(TRACKER_STATE_EVENT_TYPES))
            .order_by(TrackerEvent.created_at.desc(), TrackerEvent.id.desc())
            .limit(1)
            .scalar()
        )

    while len(items) < page_limit:
        query = (
            db.query(TrackerEvent)
            .filter(TrackerEvent.project_id == project_id)
            .filter(TrackerEvent.tracker_id == tracker_id)
        )
        if cursor is not None:
            if cursor_id is None:
                query = query.filter(TrackerEvent.created_at < cursor)
            else:
                query = query.filter(or_(
                    TrackerEvent.created_at < cursor,
                    and_(TrackerEvent.created_at == cursor, TrackerEvent.id < cursor_id),
                ))
        rows = (
            query
            .order_by(TrackerEvent.created_at.desc(), TrackerEvent.id.desc())
            .limit(page_limit + 1)
            .all()
        )
        if not rows:
            next_before = None
            next_before_id = None
            break

        restoreable_event_ids: set[int] = set()
        if audience == 'internal':
            from app.services.tracker_history import (
                is_tracker_snapshot_hash,
                snapshot_unavailable_reason,
            )
            row_ids = [int(row.id) for row in rows[:page_limit] if row.id is not None]
            stored_snapshot_ids = {
                int(event_id)
                for (event_id,) in db.query(TrackerEvent.id).filter(
                    TrackerEvent.id.in_(row_ids),
                    TrackerEvent.state_snapshot.isnot(None),
                ).all()
            } if row_ids else set()
            restoreable_event_ids = {
                int(row.id) for row in rows[:page_limit]
                if (
                    row.id is not None
                    and int(row.id) in stored_snapshot_ids
                    and is_tracker_snapshot_hash(row.state_hash)
                )
            }
        for row in rows[:page_limit]:
            cursor = row.created_at
            cursor_id = row.id
            unavailable_reason = None
            if audience == 'internal':
                unavailable_reason = snapshot_unavailable_reason(row.state_hash)
                if (
                    unavailable_reason is None
                    and row.event_type in TRACKER_STATE_EVENT_TYPES
                    and row.id not in restoreable_event_ids
                    and (row.id != current_state_event_id or row.state_hash is not None)
                ):
                    unavailable_reason = 'legacy' if row.state_hash is None else 'unavailable'
            serialized = serialize_tracker_event(
                row,
                visible_shot_ids=visible_shot_ids,
                visible_version_ids=visible_version_ids,
                audience=audience,
                restoreable=row.id in restoreable_event_ids,
                current_point=row.id == current_state_event_id,
                recovery_unavailable_reason=unavailable_reason,
            )
            if serialized is not None:
                items.append(serialized)
                if len(items) == page_limit:
                    break

        if len(items) == page_limit:
            next_before = cursor
            next_before_id = cursor_id
            break

        if len(rows) <= page_limit:
            next_before = None
            next_before_id = None
            break

        cursor = rows[page_limit - 1].created_at
        cursor_id = rows[page_limit - 1].id

    return {
        'items': items,
        'next_before': next_before,
        'next_before_id': next_before_id,
    }


def list_global_tracker_activity(
    db: Session,
    *,
    user: dict[str, Any],
    auth_mode: str | None = None,
    limit: int | None = None,
    before: float | None = None,
    before_id: int | None = None,
) -> dict[str, Any]:
    from app.services.horizons_fresh import (
        get_horizon_project_access_role,
        is_restricted_horizon_artist,
        list_visible_horizon_projects,
    )

    page_limit = max(1, min(int(limit or TRACKER_EVENT_PAGE_LIMIT_DEFAULT), TRACKER_EVENT_PAGE_LIMIT_MAX))
    projects = list_visible_horizon_projects(db, user, auth_mode=auth_mode)
    if not projects:
        return {'items': [], 'next_before': None, 'next_before_id': None}

    project_map: dict[str, HorizonProject] = {project.id: project for project in projects}
    access_roles = {
        project.id: get_horizon_project_access_role(db, project, user, auth_mode=auth_mode)
        for project in projects
    }
    project_ids = list(project_map.keys())
    trackers = (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id.in_(project_ids))
        .all()
    )
    tracker_map = {
        (tracker.project_id, tracker.id): tracker
        for tracker in trackers
    }
    visible_shot_cache: dict[tuple[str, str], set[str] | None] = {}

    def visible_shot_ids_for(project_id: str, tracker_id: str) -> set[str] | None:
        cache_key = (project_id, tracker_id)
        if cache_key not in visible_shot_cache:
            visible_shot_cache[cache_key] = tracker_activity_visible_shot_ids(
                db,
                project_id=project_id,
                tracker_id=tracker_id,
                user=user,
                access_role=access_roles.get(project_id),
            )
        return visible_shot_cache[cache_key]

    items = []
    cursor = before
    cursor_id = before_id
    next_before = None
    next_before_id = None
    batch_limit = min(max(page_limit * 3, 50), 300)

    while len(items) < page_limit:
        query = (
            db.query(TrackerEvent)
            .filter(TrackerEvent.project_id.in_(project_ids))
            .filter(TrackerEvent.event_type != 'tracker_checkpoint')
        )
        if cursor is not None:
            if cursor_id is None:
                query = query.filter(TrackerEvent.created_at < cursor)
            else:
                query = query.filter(or_(
                    TrackerEvent.created_at < cursor,
                    and_(TrackerEvent.created_at == cursor, TrackerEvent.id < cursor_id),
                ))

        rows = (
            query
            .order_by(TrackerEvent.created_at.desc(), TrackerEvent.id.desc())
            .limit(batch_limit)
            .all()
        )
        if not rows:
            next_before = None
            next_before_id = None
            break

        for row in rows:
            cursor = row.created_at
            cursor_id = row.id
            project = project_map.get(row.project_id)
            tracker = tracker_map.get((row.project_id, row.tracker_id))
            if project is None or tracker is None:
                continue

            serialized = serialize_tracker_event(
                row,
                visible_shot_ids=visible_shot_ids_for(row.project_id, row.tracker_id),
                audience='restricted' if is_restricted_horizon_artist(user, access_roles.get(row.project_id)) else 'internal',
            )
            if serialized is None:
                continue

            serialized['project_title'] = project.title
            serialized['project_slug'] = project.slug
            serialized['tracker_name'] = tracker.name
            serialized['tracker_slug'] = tracker.slug
            serialized['access_role'] = access_roles.get(row.project_id)
            if isinstance(serialized.get('target'), dict):
                serialized['target']['tracker_ref'] = tracker.name
                serialized['target']['tracker_slug'] = tracker.slug
            items.append(serialized)
            if len(items) == page_limit:
                break

        if len(items) == page_limit:
            next_before = cursor
            next_before_id = cursor_id
            break
        if len(rows) < batch_limit:
            next_before = None
            next_before_id = None
            break

    return {
        'items': items,
        'next_before': next_before,
        'next_before_id': next_before_id,
    }


def tracker_activity_visible_shot_ids(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    user: dict[str, Any] | None = None,
    access_role: str | None = None,
) -> set[str] | None:
    from app.services.horizons_fresh import is_restricted_horizon_artist, list_visible_horizon_shots

    if not is_restricted_horizon_artist(user, access_role):
        return None

    return {
        shot.id
        for shot in list_visible_horizon_shots(
            db,
            project_id,
            tracker_id=tracker_id,
            user=user,
            access_role=access_role,
        )
    }


def record_comment_tracker_event(
    db: Session,
    *,
    comment: Comment,
    event_type: str,
    actor_name: str,
    source: str,
    actor_id: str | None = None,
    created_at: float | None = None,
) -> TrackerEvent | None:
    if not comment.project_id:
        return None
    context = get_tracker_event_context_for_version(
        db,
        project_id=comment.project_id,
        shot_version_id=comment.horizons_shot_version_id,
        media_asset_id=comment.horizons_media_asset_id,
    )
    if context is None:
        return None
    if not comment.horizons_shot_version_id:
        # A media asset that maps to exactly one tracker version is the same
        # logical target. Persist that stable version identity so History can
        # capture and restore the comment without treating it as global media.
        comment.horizons_shot_version_id = context['shot_version_id']
        db.add(comment)
        db.flush()

    payload = {
        'shot_id': context['shot_id'],
        'shot_code': context['shot_code'],
        'version_label': context['version_label'],
    }
    if event_type == 'comment_added':
        payload['comment_preview'] = (comment.text or '').strip()[:160]

    return create_tracker_event(
        db,
        project_id=comment.project_id,
        tracker_id=context['tracker_id'],
        shot_id=context['shot_id'],
        shot_version_id=context['shot_version_id'],
        comment_id=comment.id,
        event_type=event_type,
        actor_id=actor_id,
        actor_name=actor_name,
        source=source,
        payload=payload,
        created_at=created_at or comment.created_at,
    )
