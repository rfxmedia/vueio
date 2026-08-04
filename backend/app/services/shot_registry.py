from __future__ import annotations

import time
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import MediaAsset, ShotRegistryEntry
from app.services.trackers import get_tracker_write_lock, load_tracker


def _latest_version_payload(shot: dict) -> tuple[int | None, str | None, str | None]:
    latest_version_number = None
    latest_file_path = None
    latest_media_asset_id = None
    for version in shot.get('versions', []) or []:
        version_number = (version or {}).get('version')
        if latest_version_number is None or (version_number or 0) >= latest_version_number:
            latest_version_number = version_number or 0
            latest_file_path = (version or {}).get('file_path')
            latest_media_asset_id = (version or {}).get('media_asset_id')
    return latest_version_number, latest_file_path, latest_media_asset_id


def upsert_shot_registry_entry(db: Session, *, project_id: str, tracker_name: str, shot: dict, source: str = 'tracker_json', tracker_id: str | None = None) -> ShotRegistryEntry:
    shot_id = shot.get('shot_id')
    if not shot_id:
        raise ValueError('shot_id required')
    now = time.time()
    tag = shot.get('tag') if 'tag' in shot else shot.get('category')
    tracker_filter = (
        or_(
            ShotRegistryEntry.tracker_id == tracker_id,
            (ShotRegistryEntry.tracker_id.is_(None)) & (ShotRegistryEntry.tracker_name == tracker_name),
        )
        if tracker_id
        else ShotRegistryEntry.tracker_name == tracker_name
    )
    entry = (
        db.query(ShotRegistryEntry)
        .filter(ShotRegistryEntry.project_id == project_id)
        .filter(tracker_filter)
        .filter(ShotRegistryEntry.shot_id == shot_id)
        .first()
    )
    latest_version_number, latest_file_path, latest_media_asset_id = _latest_version_payload(shot)
    if entry is None:
        entry = ShotRegistryEntry(
            id=str(uuid.uuid4()),
            project_id=project_id,
            tracker_id=tracker_id,
            tracker_name=tracker_name,
            shot_id=shot_id,
            status=shot.get('status') or 'not_started',
            description=shot.get('description'),
            category=tag,
            latest_version_number=latest_version_number,
            latest_file_path=latest_file_path,
            latest_media_asset_id=latest_media_asset_id,
            source=source,
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
    else:
        if tracker_id:
            entry.tracker_id = tracker_id
        entry.status = shot.get('status') or 'not_started'
        entry.description = shot.get('description')
        entry.category = tag
        entry.latest_version_number = latest_version_number
        entry.latest_file_path = latest_file_path
        entry.latest_media_asset_id = latest_media_asset_id
        entry.source = source
        entry.updated_at = now
        db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_shot_registry_entries(db: Session, project_id: str, tracker_name: str | None = None) -> list[ShotRegistryEntry]:
    query = db.query(ShotRegistryEntry).filter(ShotRegistryEntry.project_id == project_id)
    if tracker_name:
        query = query.filter(ShotRegistryEntry.tracker_name == tracker_name)
    return query.order_by(ShotRegistryEntry.created_at.asc()).all()


def list_horizon_shot_registry_entries(db: Session, project_id: str, tracker_name: str | None = None, *, user: dict | None = None, access_role: str | None = None) -> list[dict]:
    from app.services.horizons_fresh import get_horizon_tracker_by_ref, list_horizon_trackers, list_visible_horizon_shots

    trackers = [get_horizon_tracker_by_ref(db, project_id, tracker_name)] if tracker_name else list_horizon_trackers(db, project_id)
    entries = []
    for tracker in trackers:
        shots = list_visible_horizon_shots(db, project_id, tracker_id=tracker.id, user=user, access_role=access_role)
        for shot in shots:
            latest_version_number = None
            if shot.latest_version_label:
                label = str(shot.latest_version_label).strip().lower()
                if label.startswith('v') and label[1:].isdigit():
                    latest_version_number = int(label[1:])
            latest_file_path = None
            if shot.latest_media_asset_id:
                asset = db.query(MediaAsset).filter(MediaAsset.id == shot.latest_media_asset_id).first()
                if asset:
                    latest_file_path = asset.file_path
            entries.append({
                'id': f'horizons:{tracker.id}:{shot.id}',
                'project_id': project_id,
                'tracker_id': tracker.id,
                'tracker_name': tracker.name,
                'shot_id': shot.shot_code,
                'status': shot.status,
                'description': shot.description,
                'category': shot.category,
                'tag': shot.category,
                'latest_version_number': latest_version_number,
                'latest_file_path': latest_file_path,
                'latest_media_asset_id': shot.latest_media_asset_id,
                'source': 'horizons_db',
                'created_at': shot.created_at,
                'updated_at': shot.updated_at,
            })
    return entries


def backfill_tracker_shot_registry(db: Session, project_id: str, tracker_name: str) -> dict:
    scanned_shots = 0
    upserted_entries = 0
    with get_tracker_write_lock(project_id, tracker_name):
        tracker = load_tracker(project_id, tracker_name)
        for shot in tracker.get('shots', []) or []:
            scanned_shots += 1
            upsert_shot_registry_entry(db, project_id=project_id, tracker_name=tracker_name, shot=shot, source='tracker_json_backfill')
            upserted_entries += 1
    return {'scanned_shots': scanned_shots, 'upserted_entries': upserted_entries}
