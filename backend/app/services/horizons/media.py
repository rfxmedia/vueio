from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    Comment,
    HorizonShot,
    HorizonShotAssignee,
    HorizonShotVersion,
    MediaAsset,
)
from app.services.media_assets import is_generated_media_scope, media_asset_matches_filters

from .team import _subject_candidates_for_user, get_horizon_user_workspace_path, is_restricted_horizon_artist


def list_horizon_media_assets(db: Session, project_id: str) -> list[MediaAsset]:
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.unavailable_at.is_(None))
        .order_by(MediaAsset.created_at.asc())
        .all()
    )


def get_horizon_media_asset_by_path(db: Session, project_id: str, file_path: str) -> MediaAsset | None:
    normalized_path = (file_path or '').strip().strip('/')
    if not normalized_path:
        return None
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.file_path == normalized_path)
        .filter(MediaAsset.unavailable_at.is_(None))
        .order_by(MediaAsset.updated_at.desc())
        .first()
    )
    if asset and is_generated_media_scope(asset.storage_scope):
        return None
    return asset


def _list_visible_horizon_media_asset_ids(db: Session, project_id: str, user: dict | None = None, access_role: str | None = None) -> set[str] | None:
    if not is_restricted_horizon_artist(user, access_role):
        return None

    subject_ids = {value for _stype, value in _subject_candidates_for_user(user)}
    if not subject_ids:
        return set()

    visible_shot_ids = [
        shot.id
        for shot in db.query(HorizonShot)
        .join(HorizonShotAssignee, HorizonShotAssignee.shot_id == HorizonShot.id)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShotAssignee.user_id.in_(subject_ids))
        .distinct()
        .all()
    ]

    visible_asset_ids: set[str] = set()
    if visible_shot_ids:
        visible_asset_ids.update(
            asset_id
            for (asset_id,) in db.query(HorizonShotVersion.media_asset_id)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.shot_id.in_(visible_shot_ids))
            .filter(HorizonShotVersion.media_asset_id.isnot(None))
            .all()
            if asset_id
        )

    workspace_path = get_horizon_user_workspace_path(user)
    workspace_prefix = f'{workspace_path}/'
    visible_asset_ids.update(
        asset.id
        for asset in db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.storage_scope == 'project')
        .filter(MediaAsset.unavailable_at.is_(None))
        .all()
        if asset.id and (asset.file_path == workspace_path or str(asset.file_path or '').startswith(workspace_prefix))
    )

    from app.services.project_links import linked_virtual_paths_for_source
    from app.services.projects import load_project_links

    links = load_project_links(project_id).get('links', [])
    visible_asset_ids.update(
        asset.id
        for asset in db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.storage_scope == 'media_root')
        .filter(MediaAsset.unavailable_at.is_(None))
        .all()
        if asset.id and any(
            path == workspace_path or path.startswith(workspace_prefix)
            for path in linked_virtual_paths_for_source(links, asset.file_path)
        )
    )

    return visible_asset_ids


def can_access_horizon_media_asset_id(
    db: Session,
    project_id: str,
    asset_id: str | None,
    *,
    user: dict | None = None,
    access_role: str | None = None,
) -> bool:
    normalized_asset_id = str(asset_id or '').strip()
    if not normalized_asset_id:
        return False
    if not is_restricted_horizon_artist(user, access_role):
        return True

    if _restricted_artist_has_direct_media_access(db, project_id, normalized_asset_id, user):
        return True

    return _restricted_artist_has_comment_reference_access(
        db,
        project_id,
        normalized_asset_id,
        user,
        access_role,
    )


def _restricted_artist_has_direct_media_access(
    db: Session,
    project_id: str,
    asset_id: str,
    user: dict | None,
) -> bool:
    subject_ids = {value for _stype, value in _subject_candidates_for_user(user)}
    if not subject_ids:
        return False

    assigned_version = (
        db.query(HorizonShotVersion.id)
        .join(HorizonShot, HorizonShot.id == HorizonShotVersion.shot_id)
        .join(HorizonShotAssignee, HorizonShotAssignee.shot_id == HorizonShot.id)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.media_asset_id == asset_id)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShotAssignee.user_id.in_(subject_ids))
        .first()
    )
    if assigned_version is not None:
        return True

    workspace_path = get_horizon_user_workspace_path(user)
    workspace_prefix = f'{workspace_path}/'
    workspace_asset = (
        db.query(MediaAsset.id)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.id == asset_id)
        .filter(MediaAsset.storage_scope == 'project')
        .filter(or_(
            MediaAsset.file_path == workspace_path,
            MediaAsset.file_path.startswith(workspace_prefix),
        ))
        .first()
    )
    if workspace_asset is not None:
        return True

    from app.services.project_links import linked_virtual_paths_for_source
    from app.services.projects import load_project_links

    linked_asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.id == asset_id)
        .filter(MediaAsset.storage_scope == 'media_root')
        .filter(MediaAsset.unavailable_at.is_(None))
        .first()
    )
    if linked_asset is None:
        return False
    return any(
        path == workspace_path or path.startswith(workspace_prefix)
        for path in linked_virtual_paths_for_source(load_project_links(project_id).get('links', []), linked_asset.file_path)
    )


def _reference_targets_asset(raw_attachments: str | None, asset_id: str) -> bool:
    try:
        attachments = json.loads(raw_attachments or '[]')
    except (TypeError, ValueError):
        return False
    return any(
        isinstance(item, dict)
        and item.get('attachment_type') == 'reference'
        and item.get('target_type') == 'media_asset'
        and str(item.get('target_id') or '') == asset_id
        for item in attachments
    )


def _restricted_artist_has_comment_reference_access(
    db: Session,
    project_id: str,
    asset_id: str,
    user: dict | None,
    access_role: str | None,
) -> bool:
    comments = (
        db.query(Comment)
        .filter(Comment.project_id == project_id)
        .filter(Comment.attachments_data.isnot(None))
        .filter(Comment.attachments_data.contains(asset_id))
        .all()
    )
    for comment in comments:
        if not _reference_targets_asset(comment.attachments_data, asset_id):
            continue
        if comment.horizons_shot_version_id and can_access_horizon_shot_version_id(
            db,
            project_id,
            comment.horizons_shot_version_id,
            user=user,
            access_role=access_role,
        ):
            return True
        if comment.horizons_media_asset_id and _restricted_artist_has_direct_media_access(
            db,
            project_id,
            comment.horizons_media_asset_id,
            user,
        ):
            return True
        target_asset = get_horizon_media_asset_by_path(db, project_id, comment.file_path)
        if target_asset and _restricted_artist_has_direct_media_access(
            db,
            project_id,
            target_asset.id,
            user,
        ):
            return True
    return False


def can_access_horizon_shot_version_id(
    db: Session,
    project_id: str,
    version_id: str | None,
    *,
    user: dict | None = None,
    access_role: str | None = None,
) -> bool:
    normalized_version_id = str(version_id or '').strip()
    if not normalized_version_id:
        return False
    if not is_restricted_horizon_artist(user, access_role):
        return True

    subject_ids = {value for _stype, value in _subject_candidates_for_user(user)}
    if not subject_ids:
        return False

    visible_version = (
        db.query(HorizonShotVersion.id)
        .join(HorizonShot, HorizonShot.id == HorizonShotVersion.shot_id)
        .join(HorizonShotAssignee, HorizonShotAssignee.shot_id == HorizonShot.id)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.id == normalized_version_id)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShotAssignee.user_id.in_(subject_ids))
        .first()
    )
    return visible_version is not None


def list_visible_horizon_folder_assets(
    db: Session,
    project_id: str,
    folder_path: str,
    *,
    user: dict | None = None,
    access_role: str | None = None,
) -> list[MediaAsset]:
    normalized_folder = (folder_path or '').strip().strip('/')
    query = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.storage_scope == 'project')
        .filter(MediaAsset.unavailable_at.is_(None))
    )
    if normalized_folder:
        query = query.filter(or_(
            MediaAsset.file_path == normalized_folder,
            MediaAsset.file_path.startswith(f'{normalized_folder}/'),
        ))

    assets = query.order_by(MediaAsset.created_at.asc()).all()
    visible_asset_ids = _list_visible_horizon_media_asset_ids(db, project_id, user=user, access_role=access_role)
    if visible_asset_ids is not None:
        assets = [asset for asset in assets if asset.id in visible_asset_ids]
    return assets


def list_visible_horizon_media_assets(
    db: Session,
    project_id: str,
    *,
    user: dict | None = None,
    access_role: str | None = None,
    scope: str | None = None,
    kind: str | None = None,
) -> list[MediaAsset]:
    assets = list_horizon_media_assets(db, project_id)
    visible_asset_ids = _list_visible_horizon_media_asset_ids(db, project_id, user=user, access_role=access_role)
    if visible_asset_ids is not None:
        assets = [asset for asset in assets if asset.id in visible_asset_ids]
    if scope is not None or kind is not None:
        assets = [asset for asset in assets if media_asset_matches_filters(asset, scope=scope, kind=kind)]
    return assets


def get_visible_horizon_media_asset_by_path(db: Session, project_id: str, file_path: str, *, user: dict | None = None, access_role: str | None = None) -> MediaAsset | None:
    asset = get_horizon_media_asset_by_path(db, project_id, file_path)
    if asset is None:
        return None
    visible_asset_ids = _list_visible_horizon_media_asset_ids(db, project_id, user=user, access_role=access_role)
    if visible_asset_ids is None or asset.id in visible_asset_ids:
        return asset
    return None


def select_horizon_preview_asset(db: Session, project_id: str, *, user: dict | None = None, access_role: str | None = None) -> MediaAsset | None:
    from app.services.media_resolution import resolve_media_asset_path
    from app.services.horizons.version_publication import held_media_asset_ids_for_project

    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif', '.heic', '.heif', '.exr', '.dpx'}
    video_extensions = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.mxf', '.prores', '.r3d'}
    held_asset_ids = (
        held_media_asset_ids_for_project(db, project_id)
        if access_role == 'share'
        else set()
    )
    ranked: list[tuple[int, float, MediaAsset]] = []
    for asset in list_visible_horizon_media_assets(db, project_id, user=user, access_role=access_role):
        if str(asset.id) in held_asset_ids:
            continue
        full_path, _job_key, _storage_scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
        ext = Path(asset.file_path or '').suffix.lower()
        if not full_path or not full_path.exists():
            continue
        if ext in image_extensions:
            rank = 0
        elif ext in video_extensions:
            rank = 1
        else:
            rank = 2
        ranked.append((rank, -(asset.updated_at or asset.created_at or 0), asset))

    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[0][2]
