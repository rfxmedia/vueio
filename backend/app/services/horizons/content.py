from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    HorizonShot,
    HorizonShotVersion,
    MediaAsset,
)
from app.services.file_operation_journal import cancel_file_operation, create_file_operation, complete_file_operation, fail_file_operation
from app.services.path_references import rewrite_project_links_payload, rewrite_project_path_references
from app.services.project_access import verify_path_in_project
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.projects import load_project_links, save_project_links

from .common import _normalize_horizon_runtime_path, _sanitize_horizon_filename
from .projects import ensure_horizon_project_runtime_dir, require_horizon_project_writable, touch_horizon_project


def _compensate_horizon_move(
    db: Session,
    operation,
    *,
    project_id: str,
    source: Path,
    destination: Path,
    links_before: dict,
    links_rewritten: bool,
    reason: str,
) -> None:
    errors = []
    if links_rewritten:
        try:
            save_project_links(project_id, links_before)
        except Exception as exc:
            errors.append(f'project links: {exc}')
    if destination.exists() and not source.exists():
        try:
            destination.rename(source)
        except OSError as exc:
            errors.append(f'filesystem: {exc}')
    if errors:
        fail_file_operation(db, operation, RuntimeError('; '.join(errors)))
    else:
        cancel_file_operation(db, operation, reason)


def create_horizon_project_folder(db: Session, project_id: str, folder_path: str) -> dict:
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    normalized_path = _normalize_horizon_runtime_path(folder_path)
    target = project_dir / normalized_path
    verify_path_in_project(target, project_dir)
    if target.exists() and not target.is_dir():
        raise HTTPException(status_code=400, detail='A file already exists at that path')
    target.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(target)
    touch_horizon_project(db, project_id)
    return {'path': normalized_path, 'created': True}


def reserve_horizon_upload_path(db: Session, project_id: str, target_folder: str | None, filename: str | None) -> tuple[Path, Path, str]:
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    normalized_folder = _normalize_horizon_runtime_path(target_folder, allow_empty=True)
    safe_name = _sanitize_horizon_filename(filename)
    target_dir = project_dir / normalized_folder if normalized_folder else project_dir
    verify_path_in_project(target_dir, project_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(target_dir)

    base_name = Path(safe_name).stem
    extension = Path(safe_name).suffix
    candidate = target_dir / safe_name
    counter = 1
    while candidate.exists():
        candidate = target_dir / f'{base_name}_{counter}{extension}'
        counter += 1
    verify_path_in_project(candidate, project_dir)
    rel_path = str(candidate.relative_to(project_dir))
    return project_dir, candidate, rel_path


def _get_horizon_asset_by_path(db: Session, project_id: str, file_path: str) -> MediaAsset | None:
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.file_path == file_path)
        .filter(MediaAsset.unavailable_at.is_(None))
        .order_by(MediaAsset.updated_at.desc())
        .first()
    )


def _horizon_asset_is_referenced(db: Session, asset_id: str) -> bool:
    shot_link = db.query(HorizonShot).filter(HorizonShot.latest_media_asset_id == asset_id).first()
    if shot_link:
        return True
    version_link = db.query(HorizonShotVersion).filter(HorizonShotVersion.media_asset_id == asset_id).first()
    return version_link is not None


def register_horizon_project_file(
    db: Session,
    project_id: str,
    file_path: str,
    *,
    commit: bool = True,
) -> MediaAsset:
    from app.services.media_assets import register_media_asset

    require_horizon_project_writable(db, project_id)
    normalized_path = _normalize_horizon_runtime_path(file_path)
    asset = register_media_asset(
        db,
        project_id,
        normalized_path,
        storage_scope='project',
        commit=commit,
    )
    if asset is None:
        raise HTTPException(status_code=404, detail='Project file not found')
    touch_horizon_project(db, project_id, commit=commit)
    return asset


def rename_horizon_project_file(db: Session, project_id: str, file_path: str, *, new_name: str) -> dict:
    normalized_path = _normalize_horizon_runtime_path(file_path)
    parent_folder = str(Path(normalized_path).parent)
    if parent_folder == '.':
        parent_folder = ''
    return move_horizon_project_file(db, project_id, normalized_path, target_folder=parent_folder, new_name=new_name)


def move_horizon_project_file(db: Session, project_id: str, source_path: str, *, target_folder: str | None = '', new_name: str | None = None) -> dict:
    from app.services.media_assets import update_media_asset_path

    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    normalized_source = _normalize_horizon_runtime_path(source_path)
    source = project_dir / normalized_source
    verify_path_in_project(source, project_dir)
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail='Project file not found')

    normalized_folder = _normalize_horizon_runtime_path(target_folder, allow_empty=True)
    target_dir = project_dir / normalized_folder if normalized_folder else project_dir
    verify_path_in_project(target_dir, project_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    final_name = _sanitize_horizon_filename(new_name or source.name)
    destination = target_dir / final_name
    verify_path_in_project(destination, project_dir)
    if destination.exists():
        raise HTTPException(status_code=400, detail='Destination already exists')

    destination_rel = str(destination.relative_to(project_dir))
    links_before = load_project_links(project_id)
    links_after, changed_links = rewrite_project_links_payload(
        links_before,
        old_path=normalized_source,
        new_path=destination_rel,
    )
    operation = create_file_operation(
        db,
        operation_type='move_file',
        project_id=project_id,
        source_path=normalized_source,
        destination_path=destination_rel,
    )
    links_rewritten = False
    try:
        source.rename(destination)
        make_project_path_smb_mutable(destination)
        stat = destination.stat()
        asset = update_media_asset_path(
            db,
            project_id,
            normalized_source,
            destination_rel,
            storage_scope='project',
            file_size=stat.st_size,
            modified_at=stat.st_mtime,
            commit=False,
        )
        if asset is None:
            asset = register_horizon_project_file(db, project_id, destination_rel, commit=False)
        rewrite_project_path_references(
            db,
            project_id,
            normalized_source,
            destination_rel,
            commit=False,
        )
        touch_horizon_project(db, project_id, commit=False)
        if changed_links:
            save_project_links(project_id, links_after)
            links_rewritten = True
        db.commit()
    except Exception:
        db.rollback()
        _compensate_horizon_move(
            db,
            operation,
            project_id=project_id,
            source=source,
            destination=destination,
            links_before=links_before,
            links_rewritten=links_rewritten,
            reason='move_file_compensated_after_failure',
        )
        raise
    complete_file_operation(db, operation)
    return {'from_path': normalized_source, 'path': destination_rel, 'asset': asset}


def delete_horizon_project_file(db: Session, project_id: str, file_path: str) -> dict:
    from app.services.media_assets import cleanup_retired_media_asset, retire_media_asset

    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    normalized_path = _normalize_horizon_runtime_path(file_path)
    target = project_dir / normalized_path
    verify_path_in_project(target, project_dir)

    runtime_assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.file_path == normalized_path)
        .filter(MediaAsset.storage_scope == 'project')
        .filter(MediaAsset.unavailable_at.is_(None))
        .order_by(MediaAsset.created_at.asc())
        .all()
    )

    if target.exists() and not target.is_file():
        raise HTTPException(status_code=400, detail='Project file path points to a folder')
    if not target.exists() and not runtime_assets:
        raise HTTPException(status_code=404, detail='Project file not found')

    removed_asset_ids = [asset.id for asset in runtime_assets]
    operation = create_file_operation(
        db,
        operation_type='delete_file',
        project_id=project_id,
        source_path=normalized_path,
    )
    for asset in runtime_assets:
        retire_media_asset(db, asset, 'deleted')
    db.commit()
    try:
        if target.exists():
            target.unlink()
    except Exception:
        for asset in runtime_assets:
            asset.unavailable_at = None
            asset.unavailable_reason = None
            asset.updated_at = time.time()
            db.add(asset)
        db.commit()
        cancel_file_operation(db, operation, 'delete_file_compensated_after_failure')
        raise
    for asset in runtime_assets:
        cleanup_retired_media_asset(db, asset)
    if runtime_assets:
        db.commit()
    touch_horizon_project(db, project_id)
    complete_file_operation(db, operation)
    return {
        'path': normalized_path,
        'removed_asset_id': removed_asset_ids[0] if removed_asset_ids else None,
        'removed_asset_ids': removed_asset_ids,
    }


def rename_horizon_project_folder(db: Session, project_id: str, folder_path: str, *, new_name: str) -> dict:
    normalized_path = _normalize_horizon_runtime_path(folder_path)
    parent_folder = str(Path(normalized_path).parent)
    if parent_folder == '.':
        parent_folder = ''
    return move_horizon_project_folder(db, project_id, normalized_path, target_folder=parent_folder, new_name=new_name)


def move_horizon_project_folder(db: Session, project_id: str, folder_path: str, *, target_folder: str | None = '', new_name: str | None = None) -> dict:
    from app.services.media_assets import update_media_assets_under_prefix

    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    normalized_source = _normalize_horizon_runtime_path(folder_path)
    source = project_dir / normalized_source
    verify_path_in_project(source, project_dir)
    if not source.exists() or not source.is_dir():
        raise HTTPException(status_code=404, detail='Project folder not found')

    normalized_folder = _normalize_horizon_runtime_path(target_folder, allow_empty=True)
    target_parent = project_dir / normalized_folder if normalized_folder else project_dir
    verify_path_in_project(target_parent, project_dir)
    target_parent.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(target_parent)

    final_name = _sanitize_horizon_filename(new_name or source.name)
    destination = target_parent / final_name
    verify_path_in_project(destination, project_dir)
    if destination.exists():
        raise HTTPException(status_code=400, detail='Destination already exists')
    if destination.resolve(strict=False) == source.resolve(strict=False):
        raise HTTPException(status_code=400, detail='Folder is already at that path')
    try:
        destination.resolve(strict=False).relative_to(source.resolve())
        raise HTTPException(status_code=400, detail='Cannot move a folder into itself')
    except ValueError:
        pass

    destination_rel = str(destination.relative_to(project_dir))
    links_before = load_project_links(project_id)
    links_after, changed_links = rewrite_project_links_payload(
        links_before,
        old_path=normalized_source,
        new_path=destination_rel,
    )
    operation = create_file_operation(
        db,
        operation_type='move_folder',
        project_id=project_id,
        source_path=normalized_source,
        destination_path=destination_rel,
    )
    links_rewritten = False
    try:
        source.rename(destination)
        make_project_path_smb_mutable(destination)
        updated_assets = update_media_assets_under_prefix(
            db,
            project_id,
            normalized_source,
            destination_rel,
            storage_scope='project',
            commit=False,
        )
        rewrite_project_path_references(
            db,
            project_id,
            normalized_source,
            destination_rel,
            moved_is_folder=True,
            commit=False,
        )
        touch_horizon_project(db, project_id, commit=False)
        if changed_links:
            save_project_links(project_id, links_after)
            links_rewritten = True
        db.commit()
    except Exception:
        db.rollback()
        _compensate_horizon_move(
            db,
            operation,
            project_id=project_id,
            source=source,
            destination=destination,
            links_before=links_before,
            links_rewritten=links_rewritten,
            reason='move_folder_compensated_after_failure',
        )
        raise
    complete_file_operation(db, operation)
    return {'from_path': normalized_source, 'path': destination_rel, 'updated_asset_ids': [asset.id for asset in updated_assets]}


def delete_horizon_project_folder(db: Session, project_id: str, folder_path: str) -> dict:
    from app.services.media_assets import cleanup_retired_media_asset, get_media_assets_under_prefix_for_scope, retire_media_asset

    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    normalized_path = _normalize_horizon_runtime_path(folder_path)
    target = project_dir / normalized_path
    verify_path_in_project(target, project_dir)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail='Project folder not found')
    assets = get_media_assets_under_prefix_for_scope(db, project_id, normalized_path, storage_scope='project')
    operation = create_file_operation(
        db,
        operation_type='delete_folder',
        project_id=project_id,
        source_path=normalized_path,
    )
    for asset in assets:
        retire_media_asset(db, asset, 'deleted')
    db.commit()
    # Directory removal is not atomic: shutil.rmtree may delete some children
    # before an error. Keep the journal pending and the assets unavailable so
    # startup repair can finish the requested delete without falsely exposing
    # paths whose bytes may already be gone.
    shutil.rmtree(target)
    for asset in assets:
        cleanup_retired_media_asset(db, asset)
    if assets:
        db.commit()
    touch_horizon_project(db, project_id)
    complete_file_operation(db, operation)
    return {'path': normalized_path, 'removed_asset_ids': [asset.id for asset in assets]}
