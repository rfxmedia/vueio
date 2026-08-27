from __future__ import annotations

from pathlib import Path

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.models import HorizonPage, HorizonShot, HorizonTracker, MediaAsset
from app.services.horizons_fresh import (
    _list_visible_horizon_media_asset_ids,
    is_restricted_horizon_artist,
    list_visible_horizon_shots,
)
from app.services.media import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

MENTION_TARGET_TYPES = ('shot', 'media_asset', 'tracker', 'page')


def _escape_like(value: str) -> str:
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _like_patterns(query: str) -> tuple[str, str]:
    escaped = _escape_like(query.lower())
    return f'{escaped}%', f'%{escaped}%'


def _group(target_type: str, rows: list[dict], limit: int) -> dict:
    return {
        'type': target_type,
        'items': rows[:limit],
        'has_more': len(rows) > limit,
    }


def _asset_kind(path: str) -> str:
    extension = Path(path or '').suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return 'image'
    if extension in VIDEO_EXTENSIONS:
        return 'video'
    if extension in AUDIO_EXTENSIONS:
        return 'audio'
    if extension == '.pdf':
        return 'pdf'
    return 'file'


def _search_shots(
    db: Session,
    project_id: str,
    *,
    query: str,
    context_tracker_id: str | None,
    limit: int,
    user: dict,
    access_role: str,
) -> dict:
    visible_ids: set[str] | None = None
    if is_restricted_horizon_artist(user, access_role):
        visible_ids = {
            shot.id
            for shot in list_visible_horizon_shots(
                db,
                project_id,
                user=user,
                access_role=access_role,
            )
        }
        if not visible_ids:
            return _group('shot', [], limit)

    shot_code = func.lower(HorizonShot.shot_code)
    rows_query = (
        db.query(HorizonShot, HorizonTracker)
        .join(
            HorizonTracker,
            (HorizonTracker.id == HorizonShot.tracker_id)
            & (HorizonTracker.project_id == project_id),
        )
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShot.archived_at.is_(None))
    )
    if visible_ids is not None:
        rows_query = rows_query.filter(HorizonShot.id.in_(visible_ids))
    if context_tracker_id:
        rows_query = rows_query.order_by(
            case((HorizonShot.tracker_id == context_tracker_id, 0), else_=1)
        )
    if query:
        prefix, substring = _like_patterns(query)
        rows_query = rows_query.filter(shot_code.like(substring, escape='\\'))
        rows_query = rows_query.order_by(case((shot_code.like(prefix, escape='\\'), 0), else_=1))
    rows = rows_query.order_by(HorizonShot.updated_at.desc(), HorizonShot.id.asc()).limit(limit + 1).all()
    return _group('shot', [
        {
            'target_type': 'shot',
            'target_id': shot.id,
            'label': shot.shot_code,
            'sublabel': tracker.name,
            'kind': 'shot',
            'tracker_id': shot.tracker_id,
            'status': shot.status,
            'latest_version_label': shot.latest_version_label,
        }
        for shot, tracker in rows
    ], limit)


def _search_media_assets(
    db: Session,
    project_id: str,
    *,
    query: str,
    limit: int,
    user: dict,
    access_role: str,
) -> dict:
    visible_ids = _list_visible_horizon_media_asset_ids(
        db,
        project_id,
        user=user,
        access_role=access_role,
    )
    if visible_ids == set():
        return _group('media_asset', [], limit)

    file_path = func.lower(MediaAsset.file_path)
    rows_query = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.unavailable_at.is_(None))
    )
    if visible_ids is not None:
        rows_query = rows_query.filter(MediaAsset.id.in_(visible_ids))
    if query:
        prefix, substring = _like_patterns(query)
        basename_prefix = f'%/{prefix}'
        rows_query = rows_query.filter(file_path.like(substring, escape='\\')).order_by(
            case((or_(
                file_path.like(prefix, escape='\\'),
                file_path.like(basename_prefix, escape='\\'),
            ), 0), else_=1)
        )
    rows = rows_query.order_by(MediaAsset.updated_at.desc(), MediaAsset.id.asc()).limit(limit + 1).all()
    return _group('media_asset', [
        {
            'target_type': 'media_asset',
            'target_id': asset.id,
            'label': Path(asset.file_path).name,
            'sublabel': str(Path(asset.file_path).parent) if str(Path(asset.file_path).parent) != '.' else 'Project file',
            'kind': _asset_kind(asset.file_path),
            'media_asset_id': asset.id,
        }
        for asset in rows
    ], limit)


def _search_trackers(
    db: Session,
    project_id: str,
    *,
    query: str,
    limit: int,
    visible_tracker_ids: set[str] | None,
) -> dict:
    if visible_tracker_ids == set():
        return _group('tracker', [], limit)
    tracker_name = func.lower(HorizonTracker.name)
    rows_query = db.query(HorizonTracker).filter(HorizonTracker.project_id == project_id)
    if visible_tracker_ids is not None:
        rows_query = rows_query.filter(HorizonTracker.id.in_(visible_tracker_ids))
    if query:
        prefix, substring = _like_patterns(query)
        rows_query = rows_query.filter(tracker_name.like(substring, escape='\\')).order_by(
            case((tracker_name.like(prefix, escape='\\'), 0), else_=1)
        )
    rows = rows_query.order_by(HorizonTracker.updated_at.desc(), HorizonTracker.id.asc()).limit(limit + 1).all()
    return _group('tracker', [
        {
            'target_type': 'tracker',
            'target_id': tracker.id,
            'label': tracker.name,
            'sublabel': 'Tracker',
            'kind': 'tracker',
            'tracker_id': tracker.id,
        }
        for tracker in rows
    ], limit)


def _search_pages(db: Session, project_id: str, *, query: str, limit: int) -> dict:
    page_title = func.lower(HorizonPage.title)
    rows_query = db.query(HorizonPage).filter(HorizonPage.project_id == project_id)
    if query:
        prefix, substring = _like_patterns(query)
        rows_query = rows_query.filter(page_title.like(substring, escape='\\')).order_by(
            case((page_title.like(prefix, escape='\\'), 0), else_=1)
        )
    rows = rows_query.order_by(HorizonPage.updated_at.desc(), HorizonPage.id.asc()).limit(limit + 1).all()
    return _group('page', [
        {
            'target_type': 'page',
            'target_id': page.id,
            'label': page.title,
            'sublabel': 'Page',
            'kind': 'page',
        }
        for page in rows
    ], limit)


def search_project_mentions(
    db: Session,
    project_id: str,
    *,
    query: str,
    target_types: tuple[str, ...],
    context_tracker_id: str | None,
    limit: int,
    user: dict,
    access_role: str,
) -> dict:
    restricted = is_restricted_horizon_artist(user, access_role)
    visible_tracker_ids: set[str] | None = None
    if restricted:
        visible_tracker_ids = {
            shot.tracker_id
            for shot in list_visible_horizon_shots(
                db,
                project_id,
                user=user,
                access_role=access_role,
            )
        }

    builders = {
        'shot': lambda: _search_shots(
            db,
            project_id,
            query=query,
            context_tracker_id=context_tracker_id,
            limit=limit,
            user=user,
            access_role=access_role,
        ),
        'media_asset': lambda: _search_media_assets(
            db,
            project_id,
            query=query,
            limit=limit,
            user=user,
            access_role=access_role,
        ),
        'tracker': lambda: _search_trackers(
            db,
            project_id,
            query=query,
            limit=limit,
            visible_tracker_ids=visible_tracker_ids,
        ),
        'page': lambda: _group('page', [], limit) if restricted else _search_pages(
            db,
            project_id,
            query=query,
            limit=limit,
        ),
    }
    return {'groups': [builders[target_type]() for target_type in MENTION_TARGET_TYPES if target_type in target_types]}
