from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.models import DownloadEvent, NotificationDelivery, TrackerEvent


TRACKER_EVENT_RETENTION_SECONDS = 180 * 24 * 60 * 60
TRACKER_EVENT_MAX_RECORDS = 50_000
NOTIFICATION_DELIVERY_RETENTION_SECONDS = 90 * 24 * 60 * 60
NOTIFICATION_DELIVERY_MAX_RECORDS = 100_000
DOWNLOAD_EVENT_RETENTION_SECONDS = 180 * 24 * 60 * 60
DOWNLOAD_EVENT_MAX_RECORDS = 10_000


def _overflow_ids(db: Session, model, *, limit: int) -> list:
    return [
        record_id
        for (record_id,) in (
            db.query(model.id)
            .order_by(model.created_at.desc(), model.id.desc())
            .offset(limit)
            .all()
        )
    ]


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
    event_ids.update(_overflow_ids(db, TrackerEvent, limit=TRACKER_EVENT_MAX_RECORDS))
    linked_deliveries = 0
    tracker_events = 0
    if event_ids:
        linked_deliveries = db.query(NotificationDelivery).filter(
            NotificationDelivery.tracker_event_id.in_(event_ids)
        ).delete(synchronize_session=False)
        tracker_events = db.query(TrackerEvent).filter(
            TrackerEvent.id.in_(event_ids)
        ).delete(synchronize_session=False)

    notification_deliveries = db.query(NotificationDelivery).filter(
        NotificationDelivery.created_at
        < current_time - NOTIFICATION_DELIVERY_RETENTION_SECONDS
    ).delete(synchronize_session=False)
    delivery_overflow = _overflow_ids(
        db,
        NotificationDelivery,
        limit=NOTIFICATION_DELIVERY_MAX_RECORDS,
    )
    if delivery_overflow:
        notification_deliveries += db.query(NotificationDelivery).filter(
            NotificationDelivery.id.in_(delivery_overflow)
        ).delete(synchronize_session=False)

    download_events = db.query(DownloadEvent).filter(
        DownloadEvent.created_at < current_time - DOWNLOAD_EVENT_RETENTION_SECONDS
    ).delete(synchronize_session=False)
    download_overflow = _overflow_ids(db, DownloadEvent, limit=DOWNLOAD_EVENT_MAX_RECORDS)
    if download_overflow:
        download_events += db.query(DownloadEvent).filter(
            DownloadEvent.id.in_(download_overflow)
        ).delete(synchronize_session=False)

    return {
        'tracker_events': tracker_events,
        'notification_deliveries': notification_deliveries + linked_deliveries,
        'download_events': download_events,
    }
