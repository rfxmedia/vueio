from __future__ import annotations

import json
import time

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Comment, DownloadEvent, HorizonTracker, NotificationDelivery, TrackerEvent, TrackerViewEvent


TRACKER_EVENT_RETENTION_SECONDS = 180 * 24 * 60 * 60
TRACKER_EVENT_MAX_RECORDS = 10_000
NOTIFICATION_DELIVERY_RETENTION_SECONDS = 90 * 24 * 60 * 60
NOTIFICATION_DELIVERY_MAX_RECORDS = 100_000
DOWNLOAD_EVENT_RETENTION_SECONDS = 180 * 24 * 60 * 60
DOWNLOAD_EVENT_MAX_RECORDS = 10_000
TRACKER_VIEW_EVENT_RETENTION_SECONDS = 180 * 24 * 60 * 60
TRACKER_VIEW_EVENT_MAX_RECORDS = 50_000


def _prune_history(db: Session, model, *, cutoff: float, limit: int) -> int:
    expired = db.query(model).filter(model.created_at < cutoff).delete(synchronize_session=False)
    overflow = db.query(model.id).order_by(model.created_at.desc(), model.id.desc()).offset(limit)
    return expired + db.query(model).filter(model.id.in_(overflow)).delete(synchronize_session=False)


def _tracker_event_overflow_ids(db: Session, *, limit: int) -> list[int]:
    ranked = (
        db.query(
            TrackerEvent.id.label('id'),
            func.row_number().over(
                partition_by=(TrackerEvent.project_id, TrackerEvent.tracker_id),
                order_by=(TrackerEvent.created_at.desc(), TrackerEvent.id.desc()),
            ).label('position'),
        )
        .subquery()
    )
    return [
        event_id
        for (event_id,) in db.query(ranked.c.id).filter(ranked.c.position > limit).all()
    ]


def _prune_orphaned_comment_attachments(db: Session, *, cutoff: float) -> None:
    from app.config import get_settings

    root = get_settings().comment_attachments_dir
    if not root.exists():
        return
    active_paths: set[str] = set()
    for (raw_attachments,) in db.query(Comment.attachments_data).filter(Comment.attachments_data.isnot(None)).all():
        try:
            attachments = json.loads(raw_attachments or '[]')
        except (TypeError, ValueError):
            continue
        if not isinstance(attachments, list):
            continue
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            if attachment.get('attachment_type') == 'reference' or attachment.get('scope') == 'project':
                continue
            rel_path = str(attachment.get('rel_path') or '').strip().replace('\\', '/')
            if rel_path:
                active_paths.add(rel_path)

    for path in root.rglob('*'):
        try:
            if not path.is_file() or path.stat().st_mtime >= cutoff:
                continue
            rel_path = path.relative_to(root).as_posix()
            if rel_path not in active_paths:
                path.unlink()
        except OSError:
            continue


def _prune_orphaned_delivery_logos(db: Session, *, cutoff: float) -> None:
    from app.config import get_settings
    from app.services.project_delivery import normalize_delivery_logo_upload_name

    root = get_settings().thumbnail_dir / 'delivery-logos'
    if not root.exists():
        return
    active_names: set[str] = set()
    for (raw_settings,) in db.query(HorizonTracker.settings_json).filter(HorizonTracker.settings_json.isnot(None)).all():
        try:
            settings = json.loads(raw_settings or '{}')
        except (TypeError, ValueError):
            continue
        name = normalize_delivery_logo_upload_name(
            (settings.get('delivery') or {}).get('logo_upload_name')
            if isinstance(settings, dict) else None
        )
        if name:
            active_names.add(name)
    for path in root.iterdir():
        try:
            if path.is_file() and path.name not in active_names and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def prune_persistent_history(db: Session, *, now: float | None = None) -> dict[str, int]:
    current_time = time.time() if now is None else now

    expired_event_ids = [
        event_id
        for (event_id,) in (
            db.query(TrackerEvent.id)
            .filter(TrackerEvent.created_at < current_time - TRACKER_EVENT_RETENTION_SECONDS)
            .all()
        )
    ]
    event_ids = set(expired_event_ids)
    # Keep a bounded recovery window per tracker so one noisy production does
    # not evict every other project's usable history.
    event_ids.update(_tracker_event_overflow_ids(db, limit=TRACKER_EVENT_MAX_RECORDS))
    linked_deliveries = 0
    tracker_events = 0
    # Keep one fixed set for both tables, but bound SQL parameters for large
    # histories (including installations using SQLite's 999-variable limit).
    event_ids = list(event_ids)
    for offset in range(0, len(event_ids), 500):
        batch = event_ids[offset:offset + 500]
        linked_deliveries += db.query(NotificationDelivery).filter(
            NotificationDelivery.tracker_event_id.in_(batch)
        ).delete(synchronize_session=False)
        tracker_events += db.query(TrackerEvent).filter(
            TrackerEvent.id.in_(batch)
        ).delete(synchronize_session=False)
    if event_ids:
        _prune_orphaned_comment_attachments(
            db,
            cutoff=current_time - TRACKER_EVENT_RETENTION_SECONDS,
        )
        _prune_orphaned_delivery_logos(
            db,
            cutoff=current_time - TRACKER_EVENT_RETENTION_SECONDS,
        )

    notification_deliveries = _prune_history(
        db,
        NotificationDelivery,
        cutoff=current_time - NOTIFICATION_DELIVERY_RETENTION_SECONDS,
        limit=NOTIFICATION_DELIVERY_MAX_RECORDS,
    )
    download_events = _prune_history(
        db,
        DownloadEvent,
        cutoff=current_time - DOWNLOAD_EVENT_RETENTION_SECONDS,
        limit=DOWNLOAD_EVENT_MAX_RECORDS,
    )
    tracker_view_events = _prune_history(
        db,
        TrackerViewEvent,
        cutoff=current_time - TRACKER_VIEW_EVENT_RETENTION_SECONDS,
        limit=TRACKER_VIEW_EVENT_MAX_RECORDS,
    )

    return {
        'tracker_events': tracker_events,
        'notification_deliveries': notification_deliveries + linked_deliveries,
        'download_events': download_events,
        'tracker_view_events': tracker_view_events,
    }
