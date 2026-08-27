from __future__ import annotations

from collections import defaultdict
import hmac
import hashlib
import json
import logging
import time
import zlib
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, undefer

from app.models import (
    Comment,
    HorizonProject,
    HorizonShot,
    HorizonShotAssignee,
    HorizonShotVersion,
    HorizonTracker,
    MediaAsset,
    ShareLink,
    ShotRegistryEntry,
    TrackerEvent,
    VersionRegistryEntry,
)


SNAPSHOT_FORMAT_VERSION = 1
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
MAX_COMPRESSED_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_SNAPSHOT_RECORDS = 50_000
TRACKER_SNAPSHOT_STORAGE_BYTES = 256 * 1024 * 1024
TRACKER_SNAPSHOT_MAX_POINTS = 1_000
SNAPSHOT_UNAVAILABLE_TOO_LARGE = 'unavailable:too_large'
SNAPSHOT_UNAVAILABLE_STORAGE_BUDGET = 'unavailable:storage_budget'
SNAPSHOT_UNAVAILABLE_CAPTURE_FAILED = 'unavailable:capture_failed'
logger = logging.getLogger('vueio.tracker_history')
TRACKER_STATE_EVENT_TYPES = frozenset({
    'assignee_changed',
    'brief_changed',
    'category_changed',
    'comment_added',
    'comment_deleted',
    'comment_resolved',
    'shot_archived',
    'shot_created',
    'shot_deleted',
    'shot_renamed',
    'shot_reordered',
    'shot_restored',
    'shots_bulk_updated',
    'shots_deleted_bulk',
    'shots_imported',
    'status_changed',
    'status_changed_bulk',
    'tracker_restored',
    'tracker_checkpoint',
    'tracker_updated',
    'version_added',
    'version_kept_internal',
    'version_published',
    'version_removed_from_shares',
    'versions_bulk_updated',
    'versions_updated',
})

TRACKER_FIELDS = ('slug', 'name', 'settings_json', 'tags_json')
SHOT_FIELDS = (
    'id', 'shot_code', 'description', 'status', 'category', 'assignee_user_id',
    'latest_version_label', 'latest_media_asset_id', 'archived_at', 'archived_by',
    'archive_reason', 'created_at', 'updated_at',
)
ASSIGNEE_FIELDS = ('id', 'shot_id', 'user_id', 'sort_order', 'created_by', 'created_at', 'updated_at')
VERSION_FIELDS = (
    'id', 'shot_id', 'label', 'media_asset_id', 'notes', 'share_state', 'published_at',
    'created_by', 'created_at', 'updated_at',
)
COMMENT_FIELDS = (
    'id', 'file_path', 'project_id', 'horizons_media_asset_id', 'horizons_shot_version_id',
    'user_name', 'timestamp', 'text', 'resolved', 'created_at', 'parent_comment_id',
    'root_comment_id', 'annotation_data', 'annotation_target', 'attachments_data',
)

class SnapshotLimitExceeded(RuntimeError):
    pass


def _state_bytes(state: dict[str, Any]) -> bytes:
    return json.dumps(state, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def _row(model: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(model, field) for field in fields}


def _append_snapshot_row(
    rows: list[dict[str, Any]],
    row: dict[str, Any],
    budget: dict[str, int],
) -> None:
    next_records = budget['records'] + 1
    next_bytes = budget['bytes'] + len(_state_bytes(row)) + 1
    if next_records > MAX_SNAPSHOT_RECORDS or next_bytes > MAX_SNAPSHOT_BYTES:
        raise SnapshotLimitExceeded
    budget['records'] = next_records
    budget['bytes'] = next_bytes
    rows.append(row)


def _payload_for(event: TrackerEvent) -> dict[str, Any]:
    try:
        payload = json.loads(event.payload_json or '{}')
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _id_chunks(values: set[Any] | list[Any], size: int = 500):
    items = list(values)
    for offset in range(0, len(items), size):
        yield items[offset:offset + size]


def _unique_tracker_asset_ids(*, project_id: str, tracker_id: str):
    tracker_asset_ids = select(HorizonShotVersion.media_asset_id).where(
        HorizonShotVersion.project_id == project_id,
        HorizonShotVersion.tracker_id == tracker_id,
        HorizonShotVersion.media_asset_id.isnot(None),
    )
    return select(HorizonShotVersion.media_asset_id).where(
        HorizonShotVersion.project_id == project_id,
        HorizonShotVersion.media_asset_id.in_(tracker_asset_ids),
    ).group_by(
        HorizonShotVersion.media_asset_id,
    ).having(
        func.count(HorizonShotVersion.id) == 1,
    )


def _unambiguous_asset_versions(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
) -> dict[str, str]:
    rows = db.query(
        HorizonShotVersion.media_asset_id,
        HorizonShotVersion.id,
    ).filter(
        HorizonShotVersion.project_id == project_id,
        HorizonShotVersion.media_asset_id.in_(_unique_tracker_asset_ids(
            project_id=project_id,
            tracker_id=tracker_id,
        )),
    ).all()
    return {
        str(asset_id): str(version_id)
        for asset_id, version_id in rows
        if asset_id and version_id
    }


def _tracker_comment_query(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
):
    asset_versions = _unambiguous_asset_versions(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
    )
    tracker_version_ids = select(HorizonShotVersion.id).where(
        HorizonShotVersion.project_id == project_id,
        HorizonShotVersion.tracker_id == tracker_id,
    )
    filters = [
        Comment.horizons_shot_version_id.in_(tracker_version_ids),
        and_(
            Comment.horizons_shot_version_id.is_(None),
            Comment.horizons_media_asset_id.in_(_unique_tracker_asset_ids(
                project_id=project_id,
                tracker_id=tracker_id,
            )),
        ),
    ]
    query = (
        db.query(Comment)
        .filter(Comment.project_id == project_id)
        .filter(or_(*filters))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    )
    return query, asset_versions


def _tracker_comments(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
) -> tuple[list[Comment], dict[str, str]]:
    query, asset_versions = _tracker_comment_query(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
    )
    return query.all(), asset_versions


def capture_tracker_state(db: Session, *, project_id: str, tracker_id: str) -> dict[str, Any]:
    tracker = (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == project_id)
        .filter(HorizonTracker.id == tracker_id)
        .first()
    )
    if tracker is None:
        raise HTTPException(status_code=404, detail='Tracker not found')

    tracker_row = _row(tracker, TRACKER_FIELDS)
    budget = {'bytes': len(_state_bytes(tracker_row)) + 1024, 'records': 0}
    shots: list[dict[str, Any]] = []
    shot_models = (
        db.query(HorizonShot)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShot.tracker_id == tracker_id)
        .order_by(HorizonShot.created_at.asc(), HorizonShot.id.asc())
        .yield_per(250)
    )
    for shot in shot_models:
        _append_snapshot_row(shots, _row(shot, SHOT_FIELDS), budget)
    shot_ids = {str(shot['id']) for shot in shots}

    assignees: list[dict[str, Any]] = []
    assignee_models = (
        db.query(HorizonShotAssignee)
        .filter(HorizonShotAssignee.project_id == project_id)
        .filter(HorizonShotAssignee.tracker_id == tracker_id)
        .order_by(HorizonShotAssignee.shot_id.asc(), HorizonShotAssignee.sort_order.asc(), HorizonShotAssignee.id.asc())
        .yield_per(250)
    )
    for assignee in assignee_models:
        if str(assignee.shot_id) in shot_ids:
            _append_snapshot_row(assignees, _row(assignee, ASSIGNEE_FIELDS), budget)

    versions: list[dict[str, Any]] = []
    version_models = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.tracker_id == tracker_id)
        .order_by(HorizonShotVersion.shot_id.asc(), HorizonShotVersion.created_at.asc(), HorizonShotVersion.id.asc())
        .yield_per(250)
    )
    for version in version_models:
        _append_snapshot_row(versions, _row(version, VERSION_FIELDS), budget)

    comment_query, asset_versions = _tracker_comment_query(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
    )
    comment_rows: list[dict[str, Any]] = []
    for comment in comment_query.yield_per(250):
        row = _row(comment, COMMENT_FIELDS)
        if not row.get('horizons_shot_version_id') and row.get('horizons_media_asset_id'):
            row['horizons_shot_version_id'] = asset_versions.get(str(row['horizons_media_asset_id']))
        _append_snapshot_row(comment_rows, row, budget)
    return {
        'format': SNAPSHOT_FORMAT_VERSION,
        'project_id': project_id,
        'tracker_id': tracker_id,
        'tracker': tracker_row,
        'shots': shots,
        'assignees': assignees,
        'versions': versions,
        'comments': comment_rows,
    }


def _capture_restore_state(db: Session, *, project_id: str, tracker_id: str) -> dict[str, Any]:
    try:
        return capture_tracker_state(db, project_id=project_id, tracker_id=tracker_id)
    except SnapshotLimitExceeded:
        raise HTTPException(
            status_code=409,
            detail='This tracker is too large to restore safely without risking newer work.',
        )
    except (TypeError, ValueError, UnicodeError):
        raise HTTPException(
            status_code=409,
            detail='Vue could not verify this tracker’s current state, so nothing was restored.',
        )


def tracker_state_hash(state: dict[str, Any]) -> str:
    return hashlib.sha256(_state_bytes(state)).hexdigest()


def is_tracker_snapshot_hash(value: str | None) -> bool:
    normalized = str(value or '')
    return len(normalized) == 64 and all(char in '0123456789abcdef' for char in normalized)


def lock_tracker_for_history(db: Session, *, project_id: str, tracker_id: str) -> HorizonTracker:
    """Use one lock order for tracker mutations, restores, and legacy Undo."""
    with db.no_autoflush:
        tracker = (
            db.query(HorizonTracker)
            .filter(HorizonTracker.project_id == project_id)
            .filter(HorizonTracker.id == tracker_id)
            .with_for_update()
            .first()
        )
    if tracker is None:
        raise HTTPException(status_code=404, detail='Tracker not found')
    # Project deletion takes the same tracker locks before marking the project
    # deleted. Recheck after the wait so an edit that began just before deletion
    # cannot resume against a project that no longer exists to users.
    from app.services.horizons.projects import get_horizon_project

    get_horizon_project(db, project_id)
    return tracker


def prepare_tracker_history_mutation(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
) -> HorizonTracker:
    """Lock first and seed a one-time before-state for existing trackers."""
    tracker = lock_tracker_for_history(db, project_id=project_id, tracker_id=tracker_id)
    initialized = (
        db.query(TrackerEvent.id)
        .filter(TrackerEvent.project_id == project_id)
        .filter(TrackerEvent.tracker_id == tracker_id)
        .filter(TrackerEvent.state_hash.isnot(None))
        .first()
    )
    if initialized is not None:
        return tracker
    event = TrackerEvent(
        project_id=project_id,
        tracker_id=tracker_id,
        event_type='tracker_checkpoint',
        actor_name='Vue',
        source='system',
        payload_json='{}',
        created_at=time.time(),
    )
    db.add(event)
    db.flush()
    capture_tracker_event_state(db, event)
    return tracker


def _encode_state(state: dict[str, Any]) -> tuple[bytes, str]:
    raw = _state_bytes(state)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise SnapshotLimitExceeded
    compressed = zlib.compress(raw, level=6)
    if len(compressed) > MAX_COMPRESSED_SNAPSHOT_BYTES:
        raise SnapshotLimitExceeded
    return compressed, hashlib.sha256(raw).hexdigest()


def _decode_state(blob: bytes | None) -> dict[str, Any]:
    if not blob:
        raise HTTPException(status_code=409, detail='This history point predates full tracker recovery.')
    if len(blob) > MAX_COMPRESSED_SNAPSHOT_BYTES:
        raise HTTPException(status_code=409, detail='This history point is too large to restore safely.')
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(bytes(blob), MAX_SNAPSHOT_BYTES + 1)
        if inflater.unconsumed_tail or len(raw) > MAX_SNAPSHOT_BYTES:
            raise HTTPException(status_code=409, detail='This history point is too large to restore safely.')
        raw += inflater.flush()
    except zlib.error:
        raise HTTPException(status_code=409, detail='This history point is damaged and cannot be restored.')
    if not inflater.eof or inflater.unused_data:
        raise HTTPException(status_code=409, detail='This history point is damaged and cannot be restored.')
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=409, detail='This history point is too large to restore safely.')
    try:
        state = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise HTTPException(status_code=409, detail='This history point is damaged and cannot be restored.')
    if not isinstance(state, dict) or state.get('format') != SNAPSHOT_FORMAT_VERSION:
        raise HTTPException(status_code=409, detail='This history point uses an unsupported format.')
    return state


def should_capture_tracker_state(event: TrackerEvent) -> bool:
    if event.event_type not in TRACKER_STATE_EVENT_TYPES:
        return False
    if event.event_type.startswith('comment_') and event.comment_id is None:
        return False
    return True


def snapshot_unavailable_reason(value: str | None) -> str | None:
    if value == SNAPSHOT_UNAVAILABLE_STORAGE_BUDGET:
        return 'expired'
    if value == SNAPSHOT_UNAVAILABLE_TOO_LARGE:
        return 'too_large'
    if value == SNAPSHOT_UNAVAILABLE_CAPTURE_FAILED:
        return 'unavailable'
    return None


def _prune_tracker_snapshot_budget(db: Session, *, project_id: str, tracker_id: str) -> int:
    rows = (
        db.query(
            TrackerEvent.id,
            func.length(TrackerEvent.state_snapshot),
        )
        .filter(TrackerEvent.project_id == project_id)
        .filter(TrackerEvent.tracker_id == tracker_id)
        .filter(TrackerEvent.state_snapshot.isnot(None))
        .order_by(TrackerEvent.created_at.desc(), TrackerEvent.id.desc())
        .all()
    )
    used_bytes = 0
    kept_points = 0
    retired_ids: list[int] = []
    for event_id, byte_count in rows:
        size = max(0, int(byte_count or 0))
        if kept_points == 0 or (
            kept_points < TRACKER_SNAPSHOT_MAX_POINTS
            and used_bytes + size <= TRACKER_SNAPSHOT_STORAGE_BYTES
        ):
            used_bytes += size
            kept_points += 1
        else:
            retired_ids.append(int(event_id))
    if retired_ids:
        for retired_id_chunk in _id_chunks(retired_ids):
            db.query(TrackerEvent).filter(TrackerEvent.id.in_(retired_id_chunk)).update(
                {
                    TrackerEvent.state_snapshot: None,
                    TrackerEvent.state_hash: SNAPSHOT_UNAVAILABLE_STORAGE_BUDGET,
                },
                synchronize_session=False,
            )
    return len(retired_ids)


def capture_tracker_event_state(db: Session, event: TrackerEvent) -> None:
    if not should_capture_tracker_state(event):
        return
    try:
        state = capture_tracker_state(db, project_id=event.project_id, tracker_id=event.tracker_id)
        event.state_snapshot, event.state_hash = _encode_state(state)
    except SnapshotLimitExceeded:
        event.state_snapshot = None
        event.state_hash = SNAPSHOT_UNAVAILABLE_TOO_LARGE
        logger.warning(
            'Skipped oversized tracker History checkpoint (project=%s tracker=%s event=%s)',
            event.project_id,
            event.tracker_id,
            event.id,
        )
    except (TypeError, ValueError, UnicodeError):
        event.state_snapshot = None
        event.state_hash = SNAPSHOT_UNAVAILABLE_CAPTURE_FAILED
        logger.warning(
            'Skipped invalid tracker History checkpoint (project=%s tracker=%s event=%s)',
            event.project_id,
            event.tracker_id,
            event.id,
        )
    db.add(event)
    db.flush()
    _prune_tracker_snapshot_budget(
        db,
        project_id=event.project_id,
        tracker_id=event.tracker_id,
    )


def _target_state(db: Session, event: TrackerEvent) -> dict[str, Any]:
    if event.state_snapshot is not None:
        if not is_tracker_snapshot_hash(event.state_hash):
            raise HTTPException(status_code=409, detail='This history point is damaged and cannot be restored.')
        state = _decode_state(event.state_snapshot)
        try:
            actual_hash = tracker_state_hash(state)
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise HTTPException(status_code=409, detail='This history point is damaged and cannot be restored.')
        if not hmac.compare_digest(actual_hash, str(event.state_hash)):
            raise HTTPException(status_code=409, detail='This history point is damaged and cannot be restored.')
        return state
    if event.state_hash == SNAPSHOT_UNAVAILABLE_TOO_LARGE:
        raise HTTPException(status_code=409, detail='This history point was too large to save safely.')
    if event.state_hash == SNAPSHOT_UNAVAILABLE_STORAGE_BUDGET:
        raise HTTPException(status_code=409, detail='This older recovery point has expired.')
    if event.state_hash:
        raise HTTPException(status_code=409, detail='This history point is unavailable.')
    raise HTTPException(status_code=409, detail='This activity predates full tracker History.')


def _map_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get('id')): item for item in items if item.get('id') is not None}


def _group_assignees(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for item in items:
        grouped[str(item.get('shot_id'))].append((int(item.get('sort_order') or 0), str(item.get('user_id') or '')))
    return {shot_id: [user_id for _order, user_id in sorted(values)] for shot_id, values in grouped.items()}


def _state_diff(current: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    current_shots = _map_by_id(current.get('shots') or [])
    target_shots = _map_by_id(target.get('shots') or [])
    current_versions = _map_by_id(current.get('versions') or [])
    target_versions = _map_by_id(target.get('versions') or [])
    current_comments = _map_by_id(current.get('comments') or [])
    target_comments = _map_by_id(target.get('comments') or [])
    current_assignees = _group_assignees(current.get('assignees') or [])
    target_assignees = _group_assignees(target.get('assignees') or [])

    shot_added = set(target_shots) - set(current_shots)
    shot_removed = set(current_shots) - set(target_shots)
    shot_updated = {
        shot_id for shot_id in set(current_shots) & set(target_shots)
        if current_shots[shot_id] != target_shots[shot_id]
    }
    order_changed = [item.get('id') for item in current.get('shots') or []] != [item.get('id') for item in target.get('shots') or []]
    assignment_shots = {
        shot_id for shot_id in set(current_assignees) | set(target_assignees)
        if current_assignees.get(shot_id, []) != target_assignees.get(shot_id, [])
    }
    version_changed = {
        version_id for version_id in set(current_versions) | set(target_versions)
        if current_versions.get(version_id) != target_versions.get(version_id)
    }
    comment_changed = {
        comment_id for comment_id in set(current_comments) | set(target_comments)
        if current_comments.get(comment_id) != target_comments.get(comment_id)
    }
    tracker_changed = current.get('tracker') != target.get('tracker')
    version_shots = {
        str((target_versions.get(version_id) or current_versions.get(version_id) or {}).get('shot_id') or '')
        for version_id in version_changed
    }
    version_to_shot = {
        version_id: str(version.get('shot_id') or '')
        for version_id, version in {**current_versions, **target_versions}.items()
    }
    comment_shots = {
        version_to_shot.get(str((target_comments.get(comment_id) or current_comments.get(comment_id) or {}).get('horizons_shot_version_id') or ''), '')
        for comment_id in comment_changed
    }
    affected_shots = (shot_added | shot_removed | shot_updated | assignment_shots | version_shots | comment_shots) - {''}

    fields: list[str] = []
    if tracker_changed:
        fields.append('Tracker settings')
    if shot_added or shot_removed or shot_updated:
        fields.append('Shots')
    if order_changed:
        fields.append('Shot order')
    if assignment_shots:
        fields.append('Assignments')
    if version_changed:
        fields.append('Versions')
    if comment_changed:
        fields.append('Comments')
    breakdown = {
        'shots': len(shot_added | shot_removed | shot_updated),
        'versions': len(version_changed),
        'comments': len(comment_changed),
        'assignments': len(assignment_shots),
        'order': 1 if order_changed else 0,
        'settings': 1 if tracker_changed else 0,
    }
    return {
        'change_count': sum(breakdown.values()),
        'shot_count': len(affected_shots),
        'fields': fields,
        'breakdown': breakdown,
        'affected_shot_ids': sorted(affected_shots),
    }


def _event_for_restore(db: Session, *, project_id: str, tracker_id: str, event_id: int, lock: bool = False) -> TrackerEvent:
    filters = (
        TrackerEvent.id == event_id,
        TrackerEvent.project_id == project_id,
        TrackerEvent.tracker_id == tracker_id,
    )
    size_query = (
        db.query(TrackerEvent.id, func.length(TrackerEvent.state_snapshot))
        .filter(*filters)
    )
    sized = (size_query.with_for_update() if lock else size_query).first()
    if sized is None:
        raise HTTPException(status_code=404, detail='History point not found')
    if sized[1] is not None and int(sized[1]) > MAX_COMPRESSED_SNAPSHOT_BYTES:
        raise HTTPException(status_code=409, detail='This history point is too large to restore safely.')

    query = (
        db.query(TrackerEvent)
        .options(undefer(TrackerEvent.state_snapshot))
        .filter(*filters)
    )
    event = (query.with_for_update() if lock else query).first()
    if event is None:
        raise HTTPException(status_code=404, detail='History point not found')
    return event


def preview_tracker_point_restore(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    event_id: int,
) -> dict[str, Any]:
    # A preview spans several tables. Use the same lock as mutations so its
    # diff and concurrency token describe one coherent tracker state.
    lock_tracker_for_history(db, project_id=project_id, tracker_id=tracker_id)
    event = _event_for_restore(db, project_id=project_id, tracker_id=tracker_id, event_id=event_id, lock=True)
    target = _target_state(db, event)
    _validate_target_state(db, target, project_id=project_id, tracker_id=tracker_id)
    current = _capture_restore_state(db, project_id=project_id, tracker_id=tracker_id)
    diff = _state_diff(current, target)
    from app.services.tracker_events import serialize_tracker_event

    summary = serialize_tracker_event(event, audience='internal')['summary']
    return {
        'event_id': event.id,
        'action': 'restore',
        'title': 'Restore tracker to this point?',
        'summary': f'Return the tracker to its state after “{summary}”.',
        'target_summary': summary,
        'target_created_at': event.created_at,
        'expected_state_hash': tracker_state_hash(current),
        'can_restore': diff['change_count'] > 0,
        **diff,
    }


def _valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


def _parsed_json(value: Any, expected_type: type) -> Any | None:
    if value in (None, ''):
        return expected_type()
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, expected_type) else None


def _validate_snapshot_files(state: dict[str, Any], *, project: HorizonProject) -> None:
    from app.config import get_settings
    from app.services.project_access import verify_path_in_project
    from app.services.project_delivery import delivery_logo_upload_path, normalize_delivery_logo_upload_name
    from app.services.projects import resolve_project_root

    settings = _parsed_json(state['tracker'].get('settings_json'), dict)
    if settings is None:
        raise HTTPException(status_code=409, detail='This history point contains invalid tracker settings.')
    delivery = settings.get('delivery') if isinstance(settings.get('delivery'), dict) else {}
    raw_logo = delivery.get('logo_upload_name')
    logo_name = normalize_delivery_logo_upload_name(raw_logo)
    if raw_logo and (not logo_name or not delivery_logo_upload_path(logo_name).is_file()):
        raise HTTPException(status_code=409, detail='A delivery logo needed by this history point no longer exists.')

    app_root = get_settings().comment_attachments_dir.resolve()
    project_root = resolve_project_root(project)
    for comment in state['comments']:
        attachments = _parsed_json(comment.get('attachments_data'), list)
        if attachments is None or not all(isinstance(item, dict) for item in attachments):
            raise HTTPException(status_code=409, detail='This history point contains invalid comment attachments.')
        attachment_ids = [item.get('id') for item in attachments]
        if (
            not all(_valid_identifier(attachment_id) for attachment_id in attachment_ids)
            or len(attachment_ids) != len(set(attachment_ids))
        ):
            raise HTTPException(status_code=409, detail='This history point contains invalid comment attachments.')
        for attachment in attachments:
            attachment_project_id = attachment.get('project_id')
            if attachment_project_id not in (None, '', project.id):
                raise HTTPException(status_code=409, detail='This history point contains an attachment from another project.')
            if attachment.get('attachment_type') == 'reference':
                continue
            rel_path = str(attachment.get('rel_path') or '').strip()
            if not rel_path:
                raise HTTPException(status_code=409, detail='This history point contains an invalid comment attachment.')
            try:
                if attachment.get('scope') == 'project':
                    target = project_root / rel_path
                    verify_path_in_project(target, project_root)
                else:
                    target = (app_root / rel_path).resolve()
                    target.relative_to(app_root)
            except (HTTPException, OSError, ValueError):
                raise HTTPException(status_code=409, detail='This history point contains an invalid comment attachment.')
            if not target.is_file():
                raise HTTPException(status_code=409, detail='A comment attachment needed by this history point no longer exists.')


def _validate_target_state(
    db: Session,
    state: dict[str, Any],
    *,
    project_id: str,
    tracker_id: str,
) -> None:
    if state.get('format') != SNAPSHOT_FORMAT_VERSION:
        raise HTTPException(status_code=409, detail='This history point uses an unsupported format.')
    if state.get('project_id') != project_id or state.get('tracker_id') != tracker_id:
        raise HTTPException(status_code=409, detail='This history point does not belong to this tracker.')
    for collection in ('shots', 'assignees', 'versions', 'comments'):
        if not isinstance(state.get(collection), list) or not all(isinstance(item, dict) for item in state[collection]):
            raise HTTPException(status_code=409, detail='This history point contains invalid tracker data.')
    if not isinstance(state.get('tracker'), dict):
        raise HTTPException(status_code=409, detail='This history point contains invalid tracker settings.')
    project = db.query(HorizonProject).filter(HorizonProject.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail='Project not found')
    tracker_state = state['tracker']
    if not _valid_identifier(tracker_state.get('name')) or not _valid_identifier(tracker_state.get('slug')):
        raise HTTPException(status_code=409, detail='This history point contains invalid tracker identity data.')
    if any(
        tracker_state.get(field) is not None and not isinstance(tracker_state.get(field), str)
        for field in ('settings_json', 'tags_json')
    ):
        raise HTTPException(status_code=409, detail='This history point contains invalid tracker settings.')
    if _parsed_json(tracker_state.get('settings_json'), dict) is None:
        raise HTTPException(status_code=409, detail='This history point contains invalid tracker settings.')
    if _parsed_json(tracker_state.get('tags_json'), list) is None:
        raise HTTPException(status_code=409, detail='This history point contains invalid tracker tags.')

    shot_ids = [item.get('id') for item in state['shots']]
    if not all(_valid_identifier(item) for item in shot_ids) or len(shot_ids) != len(set(shot_ids)):
        raise HTTPException(status_code=409, detail='This history point contains invalid shot identities.')
    shot_codes = [item.get('shot_code') for item in state['shots']]
    if not all(_valid_identifier(item) for item in shot_codes) or len(shot_codes) != len(set(shot_codes)):
        raise HTTPException(status_code=409, detail='This history point contains invalid shot names.')
    from app.services.horizons.common import SHOT_STATUSES

    if any(item.get('status') not in SHOT_STATUSES for item in state['shots']):
        raise HTTPException(status_code=409, detail='This history point contains an invalid shot status.')
    shot_id_set = set(shot_ids)

    version_ids = [item.get('id') for item in state['versions']]
    if not all(_valid_identifier(item) for item in version_ids) or len(version_ids) != len(set(version_ids)):
        raise HTTPException(status_code=409, detail='This history point contains invalid version identities.')
    if any(item.get('shot_id') not in shot_id_set for item in state['versions']):
        raise HTTPException(status_code=409, detail='This history point contains an orphaned version.')
    if any(not _valid_identifier(item.get('label')) for item in state['versions']):
        raise HTTPException(status_code=409, detail='This history point contains an invalid version label.')
    version_labels = [(item.get('shot_id'), item.get('label')) for item in state['versions']]
    if len(version_labels) != len(set(version_labels)):
        raise HTTPException(status_code=409, detail='This history point contains duplicate version labels.')
    from app.services.horizons.version_publication import VERSION_SHARE_STATES

    if any(item.get('share_state') not in VERSION_SHARE_STATES for item in state['versions']):
        raise HTTPException(status_code=409, detail='This history point contains invalid version visibility.')

    versions_by_shot = defaultdict(dict)
    for item in state['versions']:
        versions_by_shot[item['shot_id']][item['label']] = item
    for shot in state['shots']:
        latest_label = shot.get('latest_version_label')
        latest_asset_id = shot.get('latest_media_asset_id')
        if latest_label is None:
            if latest_asset_id is not None:
                raise HTTPException(status_code=409, detail='This history point contains inconsistent latest-version data.')
            continue
        latest_version = versions_by_shot.get(shot['id'], {}).get(latest_label)
        if latest_version is None or latest_version.get('media_asset_id') != latest_asset_id:
            raise HTTPException(status_code=409, detail='This history point contains inconsistent latest-version data.')

    assignee_ids = [item.get('id') for item in state['assignees']]
    if not all(_valid_identifier(item) for item in assignee_ids) or len(assignee_ids) != len(set(assignee_ids)):
        raise HTTPException(status_code=409, detail='This history point contains invalid assignment identities.')
    if any(item.get('shot_id') not in shot_id_set for item in state['assignees']):
        raise HTTPException(status_code=409, detail='This history point contains an orphaned assignment.')
    assignee_pairs = [(item.get('shot_id'), item.get('user_id')) for item in state['assignees']]
    if (
        any(not _valid_identifier(user_id) for _shot_id, user_id in assignee_pairs)
        or len(assignee_pairs) != len(set(assignee_pairs))
        or any(not isinstance(item.get('sort_order'), int) or isinstance(item.get('sort_order'), bool) for item in state['assignees'])
    ):
        raise HTTPException(status_code=409, detail='This history point contains invalid assignments.')
    assignees_by_shot: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in state['assignees']:
        assignees_by_shot[item['shot_id']].append(item)
    for shot in state['shots']:
        ordered = sorted(
            assignees_by_shot.get(shot['id'], []),
            key=lambda item: (item['sort_order'], item['id']),
        )
        expected_primary = ordered[0]['user_id'] if ordered else None
        if shot.get('assignee_user_id') != expected_primary:
            raise HTTPException(status_code=409, detail='This history point contains inconsistent assignments.')
    if assignee_pairs:
        from app.services.horizons.projects import get_horizon_project_access_role
        from app.services.horizons.team import get_horizon_assignable_user

        for user_id in {user_id for _shot_id, user_id in assignee_pairs}:
            user = get_horizon_assignable_user(user_id)
            if user is None or get_horizon_project_access_role(db, project, user) is None:
                raise HTTPException(
                    status_code=409,
                    detail='A team member assigned in this history point no longer has project access.',
                )

    version_id_set = set(version_ids)
    comment_ids = [item.get('id') for item in state['comments']]
    if (
        any(not isinstance(comment_id, int) or isinstance(comment_id, bool) or comment_id <= 0 for comment_id in comment_ids)
        or len(comment_ids) != len(set(comment_ids))
    ):
        raise HTTPException(status_code=409, detail='This history point contains invalid comment identities.')
    if any(item.get('project_id') != project_id for item in state['comments']):
        raise HTTPException(status_code=409, detail='This history point contains a comment from another project.')
    if any(item.get('horizons_shot_version_id') not in version_id_set for item in state['comments']):
        raise HTTPException(status_code=409, detail='This history point contains an orphaned comment.')
    comment_id_set = set(comment_ids)
    if any(
        reference is not None
        and (not isinstance(reference, int) or isinstance(reference, bool) or reference not in comment_id_set)
        for item in state['comments']
        for reference in (item.get('parent_comment_id'), item.get('root_comment_id'))
    ):
        raise HTTPException(status_code=409, detail='This history point contains an invalid comment thread.')
    comments_by_id = {item['id']: item for item in state['comments']}
    for item in state['comments']:
        comment_id = item['id']
        parent_id = item.get('parent_comment_id')
        root_id = item.get('root_comment_id') or parent_id
        if parent_id == comment_id or root_id == comment_id:
            raise HTTPException(status_code=409, detail='This history point contains an invalid comment thread.')
        if root_id is None:
            continue
        root = comments_by_id[root_id]
        if root.get('parent_comment_id') is not None or root.get('root_comment_id') is not None:
            raise HTTPException(status_code=409, detail='This history point contains an invalid comment thread.')
        if parent_id is not None:
            parent = comments_by_id[parent_id]
            parent_root_id = parent.get('root_comment_id') or parent.get('parent_comment_id') or parent['id']
            if parent_root_id != root_id:
                raise HTTPException(status_code=409, detail='This history point contains an invalid comment thread.')

    media_asset_values = [
        value
        for item in state['versions'] + state['shots'] + state['comments']
        for value in (
            item.get('media_asset_id'),
            item.get('latest_media_asset_id'),
            item.get('horizons_media_asset_id'),
        )
        if value is not None
    ]
    if any(not _valid_identifier(asset_id) for asset_id in media_asset_values):
        raise HTTPException(status_code=409, detail='This history point contains an invalid media reference.')
    media_asset_ids = set(media_asset_values)
    if media_asset_ids:
        available_asset_ids: set[str] = set()
        for asset_ids in _id_chunks(media_asset_ids):
            available_asset_ids.update(
                asset_id for (asset_id,) in db.query(MediaAsset.id).filter(
                MediaAsset.project_id == project_id,
                MediaAsset.id.in_(asset_ids),
                MediaAsset.unavailable_at.is_(None),
            ).all()
            )
        if available_asset_ids != media_asset_ids:
            raise HTTPException(status_code=409, detail='Media needed by this history point no longer exists.')
    versions_by_id = {item['id']: item for item in state['versions']}
    if any(
        item.get('horizons_media_asset_id') is not None
        and versions_by_id[item['horizons_shot_version_id']].get('media_asset_id') is not None
        and item.get('horizons_media_asset_id') != versions_by_id[item['horizons_shot_version_id']].get('media_asset_id')
        for item in state['comments']
    ):
        raise HTTPException(status_code=409, detail='This history point contains an inconsistent comment target.')
    _validate_snapshot_files(state, project=project)


def _reject_target_identity_conflicts(
    db: Session,
    *,
    tracker: HorizonTracker,
    state: dict[str, Any],
) -> None:
    targets = (
        (HorizonShot, [item['id'] for item in state['shots']]),
        (HorizonShotVersion, [item['id'] for item in state['versions']]),
        (HorizonShotAssignee, [item['id'] for item in state['assignees']]),
    )
    for model, record_ids in targets:
        for record_id_chunk in _id_chunks(record_ids):
            conflict = (
                db.query(model.id)
                .filter(model.id.in_(record_id_chunk))
                .filter(or_(
                    model.project_id != tracker.project_id,
                    model.tracker_id != tracker.id,
                ))
                .first()
            )
            if conflict is not None:
                raise HTTPException(
                    status_code=409,
                    detail='An identity from this history point is now used elsewhere. Nothing was changed.',
                )


def _ensure_current_recovery_point(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    current: dict[str, Any],
    current_hash: str,
    actor_id: str | None,
    actor_name: str,
    source: str,
) -> TrackerEvent:
    """Guarantee that a full restore can itself be reversed before applying it."""
    _validate_target_state(db, current, project_id=project_id, tracker_id=tracker_id)
    try:
        blob, state_hash = _encode_state(current)
    except SnapshotLimitExceeded:
        raise HTTPException(
            status_code=409,
            detail='Vue could not protect the tracker’s current state, so nothing was restored.',
        )
    if state_hash != current_hash:
        raise HTTPException(status_code=409, detail='Vue could not verify the tracker’s current state. Nothing was restored.')
    checkpoint = TrackerEvent(
        project_id=project_id,
        tracker_id=tracker_id,
        event_type='tracker_checkpoint',
        actor_id=actor_id,
        actor_name=actor_name,
        source=source,
        payload_json=json.dumps({'reason': 'before_restore'}),
        state_snapshot=blob,
        state_hash=state_hash,
        created_at=time.time(),
    )
    db.add(checkpoint)
    db.flush()
    _prune_tracker_snapshot_budget(db, project_id=project_id, tracker_id=tracker_id)
    return checkpoint


def _completed_restore_result(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    event_id: int,
    current_hash: str,
) -> tuple[TrackerEvent, dict[str, Any]] | None:
    latest = (
        db.query(TrackerEvent)
        .filter(TrackerEvent.project_id == project_id)
        .filter(TrackerEvent.tracker_id == tracker_id)
        .filter(TrackerEvent.event_type.in_(TRACKER_STATE_EVENT_TYPES))
        .order_by(TrackerEvent.created_at.desc(), TrackerEvent.id.desc())
        .with_for_update()
        .first()
    )
    if (
        latest is None
        or latest.event_type != 'tracker_restored'
        or latest.state_hash != current_hash
        or not is_tracker_snapshot_hash(latest.state_hash)
    ):
        return None
    payload = _payload_for(latest)
    try:
        restored_to_event_id = int(payload.get('restored_to_event_id'))
    except (TypeError, ValueError):
        return None
    if restored_to_event_id != event_id:
        return None

    breakdown_payload = payload.get('breakdown')
    try:
        breakdown = {
            key: max(0, int((breakdown_payload or {}).get(key) or 0))
            for key in ('shots', 'versions', 'comments', 'assignments', 'order', 'settings')
        } if isinstance(breakdown_payload, dict) else {}
        change_count = max(0, int(payload.get('count') or 0))
        shot_count = max(0, int(payload.get('shot_count') or 0))
    except (TypeError, ValueError):
        return None
    fields = payload.get('fields')
    return latest, {
        'change_count': change_count,
        'shot_count': shot_count,
        'fields': (
            [str(field) for field in fields if str(field).strip()]
            if isinstance(fields, list)
            else []
        ),
        'breakdown': breakdown,
        # A replay only needs to reproduce the user-visible outcome. Avoid
        # persisting internal shot identifiers in the tracker-level event.
        'affected_shot_ids': [],
    }


def _allocate_postgres_comment_ids(db: Session, count: int) -> list[int]:
    allocated: list[int] = []
    while len(allocated) < count:
        needed = count - len(allocated)
        candidates = [
            int(value)
            for value in db.execute(
                text(
                    "SELECT nextval(pg_get_serial_sequence('comments', 'id')) "
                    'FROM generate_series(1, :count)'
                ),
                {'count': needed},
            ).scalars().all()
        ]
        conflicts: set[int] = set()
        for candidate_chunk in _id_chunks(candidates):
            conflicts.update(
                int(comment_id)
                for (comment_id,) in db.query(Comment.id).filter(Comment.id.in_(candidate_chunk)).all()
            )
        allocated.extend(candidate for candidate in candidates if candidate not in conflicts)
    return allocated


def _apply_tracker_state(db: Session, *, tracker: HorizonTracker, state: dict[str, Any]) -> None:
    _validate_target_state(db, state, project_id=tracker.project_id, tracker_id=tracker.id)
    tracker_state = state['tracker']
    target_name = tracker_state['name'].strip()
    target_slug = tracker_state['slug'].strip()
    identity_conflict = db.query(HorizonTracker.id).filter(
        HorizonTracker.project_id == tracker.project_id,
        HorizonTracker.id != tracker.id,
        or_(
            func.lower(HorizonTracker.name) == target_name.lower(),
            HorizonTracker.slug == target_slug,
        ),
    ).first()
    if identity_conflict:
        raise HTTPException(status_code=409, detail='Another tracker now uses the name or URL from this history point.')
    _reject_target_identity_conflicts(db, tracker=tracker, state=state)

    current_comments, _asset_versions = _tracker_comments(
        db,
        project_id=tracker.project_id,
        tracker_id=tracker.id,
    )
    target_comment_ids = {int(item['id']) for item in state.get('comments') or []}
    from app.services.comments import preserve_comment_attachments

    for comment in current_comments:
        preserve_comment_attachments(comment)
        db.delete(comment)
    db.query(HorizonShotAssignee).filter(
        HorizonShotAssignee.project_id == tracker.project_id,
        HorizonShotAssignee.tracker_id == tracker.id,
    ).delete(synchronize_session=False)
    db.query(HorizonShotVersion).filter(
        HorizonShotVersion.project_id == tracker.project_id,
        HorizonShotVersion.tracker_id == tracker.id,
    ).delete(synchronize_session=False)
    db.query(HorizonShot).filter(
        HorizonShot.project_id == tracker.project_id,
        HorizonShot.tracker_id == tracker.id,
    ).delete(synchronize_session=False)
    db.flush()

    from app.services.horizons.trackers import tracker_settings_for
    from app.services.project_delivery import preserve_delivery_logo_upload

    preserve_delivery_logo_upload(tracker_settings_for(tracker)['delivery']['logo_upload_name'])
    previous_name = tracker.name
    for field in TRACKER_FIELDS:
        setattr(tracker, field, tracker_state.get(field))
    if tracker.name != previous_name:
        db.query(ShareLink).filter(
            ShareLink.project_id == tracker.project_id,
            ShareLink.share_type == 'tracker',
            ShareLink.tracker_id == tracker.id,
        ).update({ShareLink.tracker_name: tracker.name}, synchronize_session=False)
        db.query(ShotRegistryEntry).filter(
            ShotRegistryEntry.project_id == tracker.project_id,
            ShotRegistryEntry.tracker_id == tracker.id,
        ).update({ShotRegistryEntry.tracker_name: tracker.name}, synchronize_session=False)
        db.query(VersionRegistryEntry).filter(
            VersionRegistryEntry.project_id == tracker.project_id,
            VersionRegistryEntry.tracker_id == tracker.id,
        ).update({VersionRegistryEntry.tracker_name: tracker.name}, synchronize_session=False)
    tracker.updated_at = time.time()
    db.add(tracker)

    for item in state.get('shots') or []:
        db.add(HorizonShot(project_id=tracker.project_id, tracker_id=tracker.id, **{field: item.get(field) for field in SHOT_FIELDS}))
    db.flush()
    for item in state.get('assignees') or []:
        db.add(HorizonShotAssignee(
            project_id=tracker.project_id,
            tracker_id=tracker.id,
            **{field: item.get(field) for field in ASSIGNEE_FIELDS},
        ))
    for item in state.get('versions') or []:
        db.add(HorizonShotVersion(
            project_id=tracker.project_id,
            tracker_id=tracker.id,
            **{field: item.get(field) for field in VERSION_FIELDS},
        ))
    db.flush()

    if db.get_bind().dialect.name == 'postgresql':
        # Comment IDs are global. Let PostgreSQL's sequence allocate every
        # restored ID so a comment created concurrently can never collide with
        # a manually selected value. History links and reply threads are
        # remapped below in the same transaction.
        id_map = dict(zip(
            sorted(target_comment_ids),
            _allocate_postgres_comment_ids(db, len(target_comment_ids)),
        ))
    else:
        conflicts: set[int] = set()
        for comment_id_chunk in _id_chunks(target_comment_ids):
            conflicts.update(
                int(comment_id)
                for (comment_id,) in db.query(Comment.id).filter(Comment.id.in_(comment_id_chunk)).all()
            )
        id_map = {comment_id: comment_id for comment_id in target_comment_ids}
        if conflicts:
            next_id = int(db.query(func.max(Comment.id)).scalar() or 0) + 1
            for comment_id in sorted(conflicts):
                while next_id in target_comment_ids or next_id in id_map.values():
                    next_id += 1
                id_map[comment_id] = next_id
                next_id += 1
    for item in state.get('comments') or []:
        values = {field: item.get(field) for field in COMMENT_FIELDS}
        values['id'] = id_map[int(item['id'])]
        for field in ('parent_comment_id', 'root_comment_id'):
            if values[field] is not None:
                values[field] = id_map[int(values[field])]
        db.add(Comment(**values))
    db.flush()
    if id_map:
        # PostgreSQL assigns fresh global comment IDs on every restore. Keep
        # the historical ID privately in the event payload so restoring away
        # and back can retarget comment activity repeatedly, rather than
        # leaving it attached to the first now-deleted replacement ID.
        linked_events = db.query(TrackerEvent).filter(
            TrackerEvent.project_id == tracker.project_id,
            TrackerEvent.tracker_id == tracker.id,
            TrackerEvent.comment_id.isnot(None),
        ).all()
        for linked_event in linked_events:
            payload = _payload_for(linked_event)
            origin_value = payload.get('_history_comment_id', linked_event.comment_id)
            try:
                origin_id = int(origin_value)
            except (TypeError, ValueError):
                continue
            restored_id = id_map.get(origin_id)
            if restored_id is None:
                continue
            payload['_history_comment_id'] = origin_id
            linked_event.comment_id = str(restored_id)
            linked_event.payload_json = json.dumps(payload)
            db.add(linked_event)
def restore_tracker_to_point(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    event_id: int,
    expected_state_hash: str,
    actor_id: str | None,
    actor_name: str,
    source: str,
) -> tuple[TrackerEvent, dict[str, Any]]:
    tracker = lock_tracker_for_history(db, project_id=project_id, tracker_id=tracker_id)
    event = _event_for_restore(db, project_id=project_id, tracker_id=tracker_id, event_id=event_id, lock=True)
    current = _capture_restore_state(db, project_id=project_id, tracker_id=tracker_id)
    current_hash = tracker_state_hash(current)
    if not expected_state_hash or current_hash != expected_state_hash:
        completed = _completed_restore_result(
            db,
            project_id=project_id,
            tracker_id=tracker_id,
            event_id=event_id,
            current_hash=current_hash,
        )
        if completed is not None:
            return completed
        raise HTTPException(status_code=409, detail='The tracker changed after you opened this preview. Review the restore again.')
    target = _target_state(db, event)
    _validate_target_state(db, target, project_id=project_id, tracker_id=tracker_id)
    diff = _state_diff(current, target)
    if not diff['change_count']:
        raise HTTPException(status_code=409, detail='This tracker is already at that history point.')

    _ensure_current_recovery_point(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
        current=current,
        current_hash=current_hash,
        actor_id=actor_id,
        actor_name=actor_name,
        source=source,
    )
    _apply_tracker_state(db, tracker=tracker, state=target)
    project = db.query(HorizonProject).filter(HorizonProject.id == project_id).with_for_update().first()
    if project is None:
        raise HTTPException(status_code=404, detail='Project not found')
    now = time.time()
    project.updated_at = now
    db.add(project)
    db.flush()

    from app.services.tracker_events import create_tracker_event, serialize_tracker_event

    target_summary = serialize_tracker_event(event, audience='internal')['summary']
    restored_event = create_tracker_event(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
        event_type='tracker_restored',
        actor_id=actor_id,
        actor_name=actor_name,
        source=source,
        payload={
            'restored_to_event_id': event.id,
            'restored_to_summary': target_summary,
            'count': diff['change_count'],
            'shot_count': diff['shot_count'],
            'fields': diff['fields'],
            'breakdown': diff['breakdown'],
        },
        created_at=now,
    )
    return restored_event, diff
