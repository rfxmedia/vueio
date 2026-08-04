from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import HorizonShotVersion, HorizonTracker, MediaAsset

from .tracker_settings import tracker_settings_for

VERSION_SHARE_STATE_PUBLISHED = 'published'
VERSION_SHARE_STATE_PENDING = 'pending'
VERSION_SHARE_STATE_INTERNAL = 'internal'
VERSION_SHARE_STATES = {
    VERSION_SHARE_STATE_PUBLISHED,
    VERSION_SHARE_STATE_PENDING,
    VERSION_SHARE_STATE_INTERNAL,
}


def normalize_version_share_state(value: Any) -> str:
    state = str(value or '').strip().lower()
    if not state:
        return VERSION_SHARE_STATE_PUBLISHED
    # Unknown persisted values must fail closed so malformed data cannot surface
    # media through a share.
    return state if state in VERSION_SHARE_STATES else VERSION_SHARE_STATE_INTERNAL


def version_share_state(version: HorizonShotVersion | dict | None) -> str:
    if version is None:
        return VERSION_SHARE_STATE_PUBLISHED
    value = version.get('share_state') if isinstance(version, dict) else getattr(version, 'share_state', None)
    return normalize_version_share_state(value)


def version_is_published(version: HorizonShotVersion | dict | None) -> bool:
    return version_share_state(version) == VERSION_SHARE_STATE_PUBLISHED


def initial_version_publication(tracker: HorizonTracker, *, now: float | None = None) -> tuple[str, float | None]:
    review_enabled = bool(tracker_settings_for(tracker).get('version_review', {}).get('enabled'))
    if review_enabled:
        return VERSION_SHARE_STATE_PENDING, None
    return VERSION_SHARE_STATE_PUBLISHED, float(now if now is not None else time.time())


def version_media_is_publishable(db: Session, project_id: str, media_asset_id: str | None) -> bool:
    if not media_asset_id:
        return False
    return (
        db.query(MediaAsset.id)
        .filter(MediaAsset.id == media_asset_id)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.unavailable_at.is_(None))
        .first()
        is not None
    )


def version_publication_sort_key(version: HorizonShotVersion | dict) -> tuple[float, float, str]:
    if isinstance(version, dict):
        published_at = version.get('published_at')
        created_at = version.get('created_at')
        version_id = version.get('id')
    else:
        published_at = version.published_at
        created_at = version.created_at
        version_id = version.id
    return (
        float(published_at if published_at is not None else created_at or 0),
        float(created_at or 0),
        str(version_id or ''),
    )


def published_versions(versions: Iterable[HorizonShotVersion | dict]) -> list:
    return sorted(
        [version for version in versions if version_is_published(version)],
        key=version_publication_sort_key,
    )


def published_version_ids_for_tracker(db: Session, project_id: str, tracker_id: str) -> set[str]:
    return {
        str(version_id)
        for (version_id,) in (
            db.query(HorizonShotVersion.id)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.tracker_id == tracker_id)
            .filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
            .all()
        )
    }


def published_shot_ids_for_tracker(db: Session, project_id: str, tracker_id: str) -> set[str]:
    return {
        str(shot_id)
        for (shot_id,) in (
            db.query(HorizonShotVersion.shot_id)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.tracker_id == tracker_id)
            .filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
            .distinct()
            .all()
        )
    }


def held_media_asset_ids_for_project(db: Session, project_id: str) -> set[str]:
    """Return version-bound assets that have no published use in this project."""
    referenced = {
        str(media_asset_id)
        for (media_asset_id,) in (
            db.query(HorizonShotVersion.media_asset_id)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.media_asset_id.isnot(None))
            .distinct()
            .all()
        )
    }
    published = {
        str(media_asset_id)
        for (media_asset_id,) in (
            db.query(HorizonShotVersion.media_asset_id)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.media_asset_id.isnot(None))
            .filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
            .distinct()
            .all()
        )
    }
    return referenced - published


def held_media_paths_for_project(db: Session, project_id: str) -> set[Path]:
    """Resolve held-only version assets once for path-based share boundaries."""
    held_ids = held_media_asset_ids_for_project(db, project_id)
    if not held_ids:
        return set()
    from app.services.media_resolution import resolve_media_target

    paths: set[Path] = set()
    for asset in (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.id.in_(held_ids))
        .all()
    ):
        full_path, _cache_key, _scope = resolve_media_target(
            asset.file_path,
            project_id,
            asset.storage_scope,
            db=db,
        )
        if full_path:
            paths.add(full_path.resolve(strict=False))
    return paths


def latest_published_at_for_tracker(db: Session, project_id: str, tracker_id: str) -> float | None:
    value = (
        db.query(func.max(func.coalesce(HorizonShotVersion.published_at, HorizonShotVersion.created_at)))
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.tracker_id == tracker_id)
        .filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
        .scalar()
    )
    return float(value) if value is not None else None


def published_scope_summary(
    db: Session,
    project_id: str,
    *,
    tracker_ids: Iterable[str] | None = None,
) -> dict[str, int | float | None]:
    normalized_tracker_ids = [str(tracker_id) for tracker_id in tracker_ids or [] if tracker_id]
    if tracker_ids is not None and not normalized_tracker_ids:
        return {'shot_count': 0, 'version_count': 0, 'updated_at': None}
    query = (
        db.query(
            func.count(func.distinct(HorizonShotVersion.shot_id)),
            func.count(HorizonShotVersion.id),
            func.max(func.coalesce(HorizonShotVersion.published_at, HorizonShotVersion.created_at)),
        )
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
    )
    if normalized_tracker_ids:
        query = query.filter(HorizonShotVersion.tracker_id.in_(normalized_tracker_ids))
    shot_count, version_count, updated_at = query.one()
    return {
        'shot_count': int(shot_count or 0),
        'version_count': int(version_count or 0),
        'updated_at': float(updated_at) if updated_at is not None else None,
    }


def published_versions_by_shot(
    db: Session,
    project_id: str,
    tracker_id: str,
    shot_ids: Iterable[str],
) -> dict[str, list[HorizonShotVersion]]:
    normalized_shot_ids = [str(shot_id) for shot_id in shot_ids if shot_id]
    if not normalized_shot_ids:
        return {}
    versions = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.tracker_id == tracker_id)
        .filter(HorizonShotVersion.shot_id.in_(normalized_shot_ids))
        .filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
        .all()
    )
    grouped: dict[str, list[HorizonShotVersion]] = {}
    for version in versions:
        grouped.setdefault(version.shot_id, []).append(version)
    return {
        shot_id: sorted(items, key=version_publication_sort_key)
        for shot_id, items in grouped.items()
    }


def set_version_share_state(
    db: Session,
    version: HorizonShotVersion,
    state: str,
    *,
    now: float | None = None,
) -> list[HorizonShotVersion]:
    """Apply one publication decision and return every version changed by it."""
    target_state = normalize_version_share_state(state)
    if target_state == VERSION_SHARE_STATE_PENDING:
        raise ValueError('Versions can only become pending when they are created')

    # Serialize publication decisions for one shot. On PostgreSQL this prevents
    # two owners from making decisions against stale sibling state; SQLite
    # safely treats the lock hint as a no-op.
    siblings = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.project_id == version.project_id)
        .filter(HorizonShotVersion.shot_id == version.shot_id)
        .with_for_update()
        .all()
    )
    version = next((candidate for candidate in siblings if candidate.id == version.id), version)
    changed: list[HorizonShotVersion] = []
    timestamp = float(now if now is not None else time.time())
    previous_state = version_share_state(version)

    if previous_state != target_state:
        version.share_state = target_state
        version.published_at = timestamp if target_state == VERSION_SHARE_STATE_PUBLISHED else None
        version.updated_at = timestamp
        db.add(version)
        changed.append(version)
    elif target_state == VERSION_SHARE_STATE_PUBLISHED:
        # Republishing an already shared historical version makes it current
        # without introducing another state or renumbering history.
        version.published_at = timestamp
        version.updated_at = timestamp
        db.add(version)
        changed.append(version)

    if target_state != VERSION_SHARE_STATE_PUBLISHED:
        return changed

    selected_key = (float(version.created_at or 0), str(version.id or ''))
    for candidate in siblings:
        if version_share_state(candidate) != VERSION_SHARE_STATE_PENDING:
            continue
        candidate_key = (float(candidate.created_at or 0), str(candidate.id or ''))
        if candidate.id == version.id or candidate_key >= selected_key:
            continue
        candidate.share_state = VERSION_SHARE_STATE_INTERNAL
        candidate.published_at = None
        candidate.updated_at = timestamp
        db.add(candidate)
        changed.append(candidate)

    return changed
