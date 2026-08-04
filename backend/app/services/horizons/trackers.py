from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    HorizonShot,
    HorizonShotAssignee,
    HorizonShotVersion,
    HorizonTracker,
    MediaAsset,
    ShareLink,
    ShotRegistryEntry,
    VersionRegistryEntry,
)
from app.services.media import IMAGE_EXTENSIONS, PDF_EXTENSIONS, VIDEO_EXTENSIONS, needs_transcode
from app.services.media_assets import attach_canonical_media_identity
from app.services.naming import slugify
from app.services.project_delivery import delete_delivery_logo_upload

from .common import SHOT_STATUS_LABELS, SHOT_STATUS_ORDER, _normalize_horizon_tracker_tags
from .projects import get_horizon_project
from .team import get_horizon_shot_assignee_ids, is_restricted_horizon_artist, serialize_horizon_shot_assignee, serialize_horizon_shot_assignees
from .tracker_settings import normalize_tracker_settings, tracker_settings_for
from .version_publication import published_versions_by_shot

def _deserialize_horizon_tracker_tags(tracker: HorizonTracker) -> list[str]:
    raw = str(getattr(tracker, 'tags_json', None) or '').strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return _normalize_horizon_tracker_tags(data)


def _serialize_horizon_tracker_tags(
    tracker: HorizonTracker,
    shots: list[HorizonShot],
    *,
    restrict_to_visible_shots: bool = False,
) -> list[str]:
    shot_tags = _normalize_horizon_tracker_tags([shot.category for shot in shots])
    shot_tag_keys = {tag.casefold() for tag in shot_tags}
    stored_tags = _deserialize_horizon_tracker_tags(tracker)
    if restrict_to_visible_shots:
        stored_tags = [tag for tag in stored_tags if tag.casefold() in shot_tag_keys]

    ordered = _normalize_horizon_tracker_tags(stored_tags)
    ordered_keys = {tag.casefold() for tag in ordered}
    ordered.extend(tag for tag in shot_tags if tag.casefold() not in ordered_keys)
    return ordered


def list_horizon_trackers(db: Session, project_id: str) -> list[HorizonTracker]:
    get_horizon_project(db, project_id)
    return (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == project_id)
        .order_by(HorizonTracker.created_at.asc())
        .all()
    )


def get_horizon_tracker_by_ref(db: Session, project_id: str, tracker_ref: str) -> HorizonTracker:
    ref = str(tracker_ref or '').strip()
    if not ref:
        raise HTTPException(status_code=404, detail='Tracker not found')

    base_query = db.query(HorizonTracker).filter(HorizonTracker.project_id == project_id)
    tracker = base_query.filter(HorizonTracker.id == ref).first()
    if tracker:
        return tracker
    tracker = base_query.filter(HorizonTracker.slug == ref).first()
    if tracker:
        return tracker

    name_matches = base_query.filter(HorizonTracker.name == ref).order_by(HorizonTracker.created_at.asc()).limit(2).all()
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        raise HTTPException(status_code=409, detail='Tracker name is ambiguous; use the tracker id')
    raise HTTPException(status_code=404, detail='Tracker not found')


def get_horizon_tracker_for_share(db: Session, share: ShareLink) -> HorizonTracker:
    if not share.project_id:
        raise HTTPException(status_code=404, detail='Project not found')
    if share.tracker_id:
        return get_horizon_tracker(db, share.project_id, share.tracker_id)
    if not share.tracker_name:
        raise HTTPException(status_code=404, detail='Tracker not found')
    return get_horizon_tracker_by_ref(db, share.project_id, share.tracker_name)


def serialize_horizon_tracker_summary(db: Session, tracker: HorizonTracker, user: dict | None = None, access_role: str | None = None) -> dict:
    from .shots import list_visible_horizon_shots

    visible_shots = list_visible_horizon_shots(db, tracker.project_id, tracker_id=tracker.id, user=user, access_role=access_role)
    return {
        'id': tracker.id,
        'slug': tracker.slug,
        'name': tracker.name,
        'settings': tracker_settings_for(tracker),
        'shot_count': len(visible_shots),
        'created_at': tracker.created_at,
        'updated_at': tracker.updated_at,
        'source': 'horizons_db',
    }


def serialize_horizon_shot_version_media(version: HorizonShotVersion, asset: MediaAsset | None = None) -> dict:
    file_path = asset.file_path if asset else None
    ext = Path(file_path).suffix.lower() if file_path else ''
    exists = bool(asset and asset.unavailable_at is None)
    return attach_canonical_media_identity({
        'id': version.id,
        'version': version.label,
        'label': version.label,
        'path': file_path,
        'file_path': file_path,
        'media_asset_id': version.media_asset_id,
        'notes': version.notes,
        'share_state': version.share_state,
        'published_at': version.published_at,
        'created_by': version.created_by,
        'created_at': version.created_at,
        'updated_at': version.updated_at,
        'exists': exists,
        'unavailable_at': asset.unavailable_at if asset else None,
        'unavailable_reason': asset.unavailable_reason if asset else 'deleted',
        'needs_transcode': bool(file_path and needs_transcode(Path(file_path))),
        'is_video': bool(file_path and ext in VIDEO_EXTENSIONS),
        'is_image': bool(file_path and ext in IMAGE_EXTENSIONS),
        'is_pdf': bool(file_path and ext in PDF_EXTENSIONS),
    }, media_asset_id=version.media_asset_id, shot_version_id=version.id)


def _serialize_horizon_tracker_versions(db: Session, shot: HorizonShot) -> list[dict]:
    from .shots import list_horizon_shot_versions

    versions = list_horizon_shot_versions(db, shot.project_id, shot.id)
    asset_ids = [version.media_asset_id for version in versions if version.media_asset_id]
    asset_map = {}
    if asset_ids:
        asset_map = {
            asset.id: asset
            for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(asset_ids)).all()
        }
        from app.services.media_resolution import resolve_media_asset_path

        for asset in asset_map.values():
            resolve_media_asset_path(asset, project_id=shot.project_id, db=db)
    return [serialize_horizon_shot_version_media(version, asset_map.get(version.media_asset_id)) for version in versions]


def serialize_horizon_tracker_detail(
    db: Session,
    tracker: HorizonTracker,
    user: dict | None = None,
    access_role: str | None = None,
    *,
    shot_limit: int | None = None,
    version_limit: int | None = None,
    include_archived: bool = False,
) -> dict:
    from .shots import list_visible_horizon_shots

    shots = list_visible_horizon_shots(
        db,
        tracker.project_id,
        tracker_id=tracker.id,
        user=user,
        access_role=access_role,
        include_archived=include_archived,
    )
    active_shot_count = sum(1 for shot in shots if not shot.archived_at)
    archived_shot_count = sum(1 for shot in shots if shot.archived_at)
    tags = _serialize_horizon_tracker_tags(
        tracker,
        shots,
        restrict_to_visible_shots=is_restricted_horizon_artist(user, access_role),
    )
    if shot_limit and shot_limit > 0:
        shots = shots[:shot_limit]

    def shot_versions_payload(shot: HorizonShot) -> list[dict]:
        versions = _serialize_horizon_tracker_versions(db, shot)
        if version_limit and version_limit > 0:
            return versions[:version_limit]
        return versions

    return {
        'id': tracker.id,
        'slug': tracker.slug,
        'name': tracker.name,
        'settings': tracker_settings_for(tracker),
        'categories': tags,
        'tags': tags,
        'nodeViewLayout': {'zoom': 1.0, 'panX': 0, 'panY': 0, 'categoryPositions': {}, 'tagPositions': {}},
        'created_at': tracker.created_at,
        'updated_at': tracker.updated_at,
        'source': 'horizons_db',
        'shot_count': active_shot_count,
        'active_shot_count': active_shot_count,
        'archived_shot_count': archived_shot_count,
        'shot_limit': shot_limit,
        'shot_version_limit': version_limit,
        'shots': [
            {
                'id': shot.id,
                'shot_id': shot.shot_code,
                'description': shot.description,
                'status': shot.status,
                'category': shot.category,
                'tag': shot.category,
                'assignee_user_ids': get_horizon_shot_assignee_ids(shot),
                'assignees': serialize_horizon_shot_assignees(shot),
                'assignee_user_id': shot.assignee_user_id,
                'assignee': serialize_horizon_shot_assignee(shot),
                'latest_version_label': shot.latest_version_label,
                'latest_media_asset_id': shot.latest_media_asset_id,
                'archived_at': shot.archived_at,
                'archived_by': shot.archived_by,
                'archive_reason': shot.archive_reason,
                'versions': shot_versions_payload(shot),
                'created_at': shot.created_at,
                'updated_at': shot.updated_at,
            }
            for shot in shots
        ],
    }


def _build_horizon_tracker_stats_payload(
    db: Session,
    tracker: HorizonTracker,
    shots: list[HorizonShot],
    *,
    published_only: bool = False,
) -> dict:
    shot_ids = [shot.id for shot in shots]
    published_by_shot = published_versions_by_shot(db, tracker.project_id, tracker.id, shot_ids) if published_only else {}
    if published_only:
        shots = [shot for shot in shots if published_by_shot.get(shot.id)]
        latest_versions = {shot.id: published_by_shot[shot.id][-1] for shot in shots}
        latest_asset_ids = [
            version.media_asset_id
            for version in latest_versions.values()
            if version.media_asset_id
        ]
    else:
        latest_versions = {}
        latest_asset_ids = [shot.latest_media_asset_id for shot in shots if shot.latest_media_asset_id]
    asset_map = {}
    if latest_asset_ids:
        asset_map = {
            asset.id: asset
            for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(latest_asset_ids)).all()
        }
    version_count_rows = []
    if shot_ids and not published_only:
        version_count_rows = (
            db.query(HorizonShotVersion.shot_id, func.count(HorizonShotVersion.id))
            .filter(HorizonShotVersion.project_id == tracker.project_id)
            .filter(HorizonShotVersion.shot_id.in_(shot_ids))
            .group_by(HorizonShotVersion.shot_id)
            .all()
        )
    version_counts = (
        {shot_id: len(published_by_shot.get(shot_id, [])) for shot_id in shot_ids}
        if published_only
        else {shot_id: int(count or 0) for shot_id, count in version_count_rows}
    )

    from app.services.media_metadata import get_cached_video_info
    from app.services.media_resolution import resolve_media_asset_path

    media_info_cache: dict[str, dict] = {}
    total_duration = 0.0
    total_frames = 0
    shots_with_latest_video = 0
    status_counts = {status: 0 for status in SHOT_STATUS_ORDER}

    for shot in shots:
        status_counts[shot.status] = status_counts.get(shot.status, 0) + 1
        asset_id = (
            latest_versions[shot.id].media_asset_id
            if published_only and shot.id in latest_versions
            else shot.latest_media_asset_id
        )
        if not asset_id:
            continue
        asset = asset_map.get(asset_id)
        if asset is None:
            continue
        if asset_id not in media_info_cache:
            full_path, _cache_key, _storage_scope = resolve_media_asset_path(asset, project_id=tracker.project_id, db=db)
            if not full_path or not full_path.exists() or not full_path.is_file():
                media_info_cache[asset_id] = {'duration': 0, 'frames': 0}
            else:
                media_info_cache[asset_id] = get_cached_video_info(
                    db,
                    full_path,
                    asset.file_path,
                    project_id=tracker.project_id,
                    storage_scope=asset.storage_scope,
                    media_asset_id=asset.id,
                )
        info = media_info_cache[asset_id]
        duration = float(info.get('duration', 0) or 0)
        frames = int(info.get('frames', 0) or 0)
        total_duration += duration
        total_frames += frames
        if duration > 0 or frames > 0:
            shots_with_latest_video += 1

    total_versions = sum(version_counts.values())
    average_versions_per_shot = round(total_versions / len(shots), 2) if shots else 0.0
    average_shot_duration = round(total_duration / shots_with_latest_video, 2) if shots_with_latest_video else 0.0
    status_breakdown = [
        {
            'status': status,
            'label': SHOT_STATUS_LABELS.get(status, status.replace('_', ' ').title()),
            'count': status_counts.get(status, 0),
        }
        for status in SHOT_STATUS_ORDER
    ]

    return {
        'totalDuration': round(total_duration, 2),
        'totalFrames': total_frames,
        'totalShots': len(shots),
        'totalVersions': total_versions,
        'averageVersionsPerShot': average_versions_per_shot,
        'averageShotDuration': average_shot_duration,
        'statusBreakdown': status_breakdown,
        'doneShots': sum(1 for shot in shots if shot.status == 'done'),
        'computed_at': time.time(),
    }


def _deserialize_horizon_tracker_stats(tracker: HorizonTracker) -> dict | None:
    raw = str(tracker.stats_json or '').strip()
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    return data


def refresh_horizon_tracker_stats_cache(db: Session, tracker: HorizonTracker, *, commit: bool = True) -> dict:
    from .shots import list_visible_horizon_shots

    tracker_record = tracker
    shots = list_visible_horizon_shots(db, tracker_record.project_id, tracker_id=tracker_record.id)
    stats = _build_horizon_tracker_stats_payload(db, tracker_record, shots)
    tracker_record.stats_json = json.dumps(stats)
    tracker_record.stats_updated_at = stats['computed_at']
    db.add(tracker_record)
    if commit:
        db.commit()
        db.refresh(tracker_record)
    return stats


def compute_horizon_tracker_stats(
    db: Session,
    tracker: HorizonTracker,
    user: dict | None = None,
    access_role: str | None = None,
    *,
    published_only: bool = False,
) -> dict:
    from .shots import list_visible_horizon_shots

    if published_only:
        shots = list_visible_horizon_shots(db, tracker.project_id, tracker_id=tracker.id)
        return _build_horizon_tracker_stats_payload(db, tracker, shots, published_only=True)

    if is_restricted_horizon_artist(user, access_role):
        shots = list_visible_horizon_shots(db, tracker.project_id, tracker_id=tracker.id, user=user, access_role=access_role)
        return _build_horizon_tracker_stats_payload(db, tracker, shots)

    cached = _deserialize_horizon_tracker_stats(tracker)
    if cached is not None:
        return cached

    return refresh_horizon_tracker_stats_cache(db, tracker)


def get_horizon_tracker(db: Session, project_id: str, tracker_id: str) -> HorizonTracker:
    tracker = (
        db.query(HorizonTracker)
        .filter(HorizonTracker.id == tracker_id)
        .filter(HorizonTracker.project_id == project_id)
        .first()
    )
    if not tracker:
        raise HTTPException(status_code=404, detail='Horizons tracker not found')
    return tracker


def create_horizon_tracker(db: Session, *, project_id: str, name: str, slug: str | None = None) -> HorizonTracker:
    project = get_horizon_project(db, project_id)
    now = time.time()
    normalized_name = (name or '').strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail='Tracker name is required')
    if (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == project_id)
        .filter(func.lower(HorizonTracker.name) == normalized_name.lower())
        .first()
    ):
        raise HTTPException(status_code=409, detail='Tracker name already exists')

    normalized_slug = slugify(slug or normalized_name, f'tracker-{str(uuid.uuid4())[:8]}')
    if (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == project_id)
        .filter(HorizonTracker.slug == normalized_slug)
        .first()
    ):
        raise HTTPException(status_code=400, detail='Horizons tracker slug already exists')

    tracker = HorizonTracker(
        id=str(uuid.uuid4()),
        project_id=project_id,
        slug=normalized_slug,
        name=normalized_name,
        created_at=now,
        updated_at=now,
    )
    project.updated_at = now
    db.add(project)
    db.add(tracker)
    db.commit()
    db.refresh(tracker)
    return tracker


def duplicate_horizon_tracker(db: Session, project_id: str, tracker_ref: str) -> HorizonTracker:
    from .shots import list_horizon_shots

    source = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    project = get_horizon_project(db, project_id)
    existing_names = {
        str(name or '').strip().casefold()
        for (name,) in db.query(HorizonTracker.name).filter(HorizonTracker.project_id == project_id).all()
    }
    existing_slugs = {
        str(slug or '').strip().casefold()
        for (slug,) in db.query(HorizonTracker.slug).filter(HorizonTracker.project_id == project_id).all()
    }
    base_name = f'{source.name} Copy'
    copy_name = base_name
    copy_slug = slugify(copy_name, f'tracker-{str(uuid.uuid4())[:8]}')
    suffix = 2
    while copy_name.casefold() in existing_names or copy_slug.casefold() in existing_slugs:
        copy_name = f'{base_name} {suffix}'
        copy_slug = slugify(copy_name, f'tracker-{str(uuid.uuid4())[:8]}')
        suffix += 1

    now = time.time()
    duplicate_settings = tracker_settings_for(source)
    duplicate_settings['delivery']['logo_upload_name'] = ''
    duplicate = HorizonTracker(
        id=str(uuid.uuid4()),
        project_id=project_id,
        slug=copy_slug,
        name=copy_name,
        settings_json=json.dumps(duplicate_settings),
        tags_json=source.tags_json,
        stats_json=None,
        stats_updated_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(duplicate)
    db.flush()

    source_shots = list_horizon_shots(db, project_id, source.id, include_archived=True)
    source_shot_ids = [shot.id for shot in source_shots]
    assignees_by_shot: dict[str, list[HorizonShotAssignee]] = {}
    versions_by_shot: dict[str, list[HorizonShotVersion]] = {}
    if source_shot_ids:
        for assignee in (
            db.query(HorizonShotAssignee)
            .filter(HorizonShotAssignee.shot_id.in_(source_shot_ids))
            .order_by(HorizonShotAssignee.sort_order.asc(), HorizonShotAssignee.created_at.asc())
            .all()
        ):
            assignees_by_shot.setdefault(assignee.shot_id, []).append(assignee)
        for version in (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.shot_id.in_(source_shot_ids))
            .order_by(HorizonShotVersion.created_at.asc())
            .all()
        ):
            versions_by_shot.setdefault(version.shot_id, []).append(version)

    for source_shot in source_shots:
        shot_id = str(uuid.uuid4())
        copied_shot = HorizonShot(
            id=shot_id,
            project_id=project_id,
            tracker_id=duplicate.id,
            shot_code=source_shot.shot_code,
            description=source_shot.description,
            status=source_shot.status,
            category=source_shot.category,
            assignee_user_id=source_shot.assignee_user_id,
            latest_version_label=source_shot.latest_version_label,
            latest_media_asset_id=source_shot.latest_media_asset_id,
            archived_at=source_shot.archived_at,
            archived_by=source_shot.archived_by,
            archive_reason=source_shot.archive_reason,
            created_at=source_shot.created_at,
            updated_at=now,
        )
        db.add(copied_shot)

        for assignee in assignees_by_shot.get(source_shot.id, []):
            db.add(HorizonShotAssignee(
                id=str(uuid.uuid4()),
                project_id=project_id,
                tracker_id=duplicate.id,
                shot_id=shot_id,
                user_id=assignee.user_id,
                sort_order=assignee.sort_order,
                created_by=assignee.created_by,
                created_at=assignee.created_at,
                updated_at=now,
            ))

        for version in versions_by_shot.get(source_shot.id, []):
            db.add(HorizonShotVersion(
                id=str(uuid.uuid4()),
                project_id=project_id,
                tracker_id=duplicate.id,
                shot_id=shot_id,
                label=version.label,
                media_asset_id=version.media_asset_id,
                notes=version.notes,
                share_state=version.share_state,
                published_at=version.published_at,
                created_by=version.created_by,
                created_at=version.created_at,
                updated_at=now,
            ))

    project.updated_at = now
    db.add(project)
    db.commit()
    db.refresh(duplicate)
    return duplicate


def update_horizon_tracker(
    db: Session,
    project_id: str,
    tracker_ref: str,
    *,
    name: str | None = None,
    slug: str | None = None,
    tags: list | None = None,
    settings: dict | None = None,
    fields_set: set[str] | None = None,
) -> HorizonTracker:
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    project = get_horizon_project(db, project_id)
    fields = set(fields_set or set())

    previous_name = tracker.name
    if 'name' in fields:
        normalized_name = (name or '').strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail='Tracker name is required')
        existing_name = (
            db.query(HorizonTracker)
            .filter(HorizonTracker.project_id == project_id)
            .filter(HorizonTracker.id != tracker.id)
            .filter(func.lower(HorizonTracker.name) == normalized_name.lower())
            .first()
        )
        if existing_name:
            raise HTTPException(status_code=409, detail='Tracker name already exists')
        tracker.name = normalized_name
        if normalized_name != previous_name:
            (
                db.query(ShareLink)
                .filter(ShareLink.project_id == project_id)
                .filter(ShareLink.share_type == 'tracker')
                .filter(ShareLink.tracker_id == tracker.id)
                .update({ShareLink.tracker_name: normalized_name}, synchronize_session=False)
            )
            (
                db.query(VersionRegistryEntry)
                .filter(VersionRegistryEntry.project_id == project_id)
                .filter(VersionRegistryEntry.tracker_id == tracker.id)
                .update({VersionRegistryEntry.tracker_name: normalized_name}, synchronize_session=False)
            )
            (
                db.query(ShotRegistryEntry)
                .filter(ShotRegistryEntry.project_id == project_id)
                .filter(ShotRegistryEntry.tracker_id == tracker.id)
                .update({ShotRegistryEntry.tracker_name: normalized_name}, synchronize_session=False)
            )
    if 'slug' in fields:
        normalized_slug = slugify(slug or tracker.name, f'tracker-{str(uuid.uuid4())[:8]}')
        existing = (
            db.query(HorizonTracker)
            .filter(HorizonTracker.project_id == project_id)
            .filter(HorizonTracker.slug == normalized_slug)
            .first()
        )
        if existing and existing.id != tracker.id:
            raise HTTPException(status_code=400, detail='Horizons tracker slug already exists')
        tracker.slug = normalized_slug
    if 'tags' in fields:
        tracker.tags_json = json.dumps(_normalize_horizon_tracker_tags(tags or []))
    if 'settings' in fields:
        tracker.settings_json = json.dumps(normalize_tracker_settings(settings))

    now = time.time()
    tracker.updated_at = now
    project.updated_at = now
    db.add(tracker)
    db.add(project)
    db.commit()
    db.refresh(tracker)
    return tracker


def delete_horizon_tracker(db: Session, project_id: str, tracker_ref: str) -> tuple[str, str]:
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    tracker_id = tracker.id
    tracker_name = tracker.name
    delivery_logo = tracker_settings_for(tracker)['delivery']['logo_upload_name']

    db.query(HorizonShotAssignee).filter(HorizonShotAssignee.tracker_id == tracker_id).delete(synchronize_session=False)
    db.query(HorizonShotVersion).filter(HorizonShotVersion.tracker_id == tracker_id).delete(synchronize_session=False)
    db.query(HorizonShot).filter(HorizonShot.tracker_id == tracker_id).delete(synchronize_session=False)
    db.query(VersionRegistryEntry).filter(VersionRegistryEntry.tracker_id == tracker_id).delete(synchronize_session=False)
    db.query(ShotRegistryEntry).filter(ShotRegistryEntry.tracker_id == tracker_id).delete(synchronize_session=False)

    project = get_horizon_project(db, project_id)
    project.updated_at = time.time()
    db.add(project)
    db.delete(tracker)
    db.commit()
    delete_delivery_logo_upload(delivery_logo)
    return tracker_id, tracker_name
