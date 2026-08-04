from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import FileOperationJournal
from app.services.project_access import verify_path_in_project
from app.services.projects import get_project_dir, resolve_project_root

PENDING_STATUSES = {'pending', 'in_progress'}
MANUAL_REVIEW_STATUS = 'manual_review'


def create_file_operation(
    db: Session,
    *,
    operation_type: str,
    project_id: str,
    source_path: str | None = None,
    destination_path: str | None = None,
    payload: dict | None = None,
) -> FileOperationJournal:
    now = time.time()
    operation = FileOperationJournal(
        id=str(uuid.uuid4()),
        operation_type=operation_type,
        project_id=project_id,
        source_path=source_path,
        destination_path=destination_path,
        status='pending',
        payload_json=json.dumps(payload or {}, sort_keys=True),
        created_at=now,
        updated_at=now,
    )
    db.add(operation)
    db.commit()
    db.refresh(operation)
    return operation


def complete_file_operation(db: Session, operation: FileOperationJournal) -> None:
    operation.status = 'complete'
    operation.error_text = None
    operation.updated_at = time.time()
    db.add(operation)
    db.commit()


def fail_file_operation(db: Session, operation: FileOperationJournal, exc: BaseException) -> None:
    operation.status = MANUAL_REVIEW_STATUS
    operation.error_text = str(exc)
    operation.updated_at = time.time()
    db.add(operation)
    db.commit()


def requeue_file_operation(db: Session, operation: FileOperationJournal, reason: str | None = None) -> None:
    if operation.status != MANUAL_REVIEW_STATUS:
        raise RuntimeError('Only manual-review file operations can be requeued')
    operation.status = 'pending'
    operation.error_text = reason
    operation.updated_at = time.time()
    db.add(operation)
    db.commit()


def cancel_file_operation(db: Session, operation: FileOperationJournal, reason: str) -> None:
    operation.status = 'cancelled'
    operation.error_text = reason
    operation.updated_at = time.time()
    db.add(operation)
    db.commit()


def _project_path(project_dir: Path, rel_path: str | None) -> Path | None:
    if not rel_path:
        return None
    target = project_dir / rel_path.strip().strip('/')
    verify_path_in_project(target, project_dir)
    return target


def _operation_project_dir(db: Session, operation: FileOperationJournal) -> Path:
    from app.models import HorizonProject

    project = db.query(HorizonProject).filter(HorizonProject.id == operation.project_id).first()
    return resolve_project_root(project) if project is not None else get_project_dir(operation.project_id)


def _apply_move(db: Session, operation: FileOperationJournal, *, is_folder: bool) -> None:
    project_dir = _operation_project_dir(db, operation)
    source = _project_path(project_dir, operation.source_path)
    destination = _project_path(project_dir, operation.destination_path)
    if source is None or destination is None:
        raise RuntimeError('Move operation is missing source or destination')

    source_exists = source.exists() and (source.is_dir() if is_folder else source.is_file())
    destination_exists = destination.exists() and (destination.is_dir() if is_folder else destination.is_file())
    if source_exists and destination_exists:
        raise RuntimeError('Move recovery found both source and destination paths')
    if source_exists:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    elif not destination_exists:
        raise RuntimeError('Move recovery found neither source nor destination path')


def _apply_delete(db: Session, operation: FileOperationJournal, *, is_folder: bool) -> None:
    project_dir = _operation_project_dir(db, operation)
    target = _project_path(project_dir, operation.source_path)
    if target is None:
        raise RuntimeError('Delete operation is missing target path')
    if not target.exists():
        return
    if is_folder:
        if not target.is_dir():
            raise RuntimeError('Delete-folder recovery target is not a folder')
        shutil.rmtree(target)
    else:
        if not target.is_file():
            raise RuntimeError('Delete-file recovery target is not a file')
        target.unlink()


def _apply_project_delete(db: Session, operation: FileOperationJournal) -> None:
    # External client folders are never owned by Vue and must never be deleted.
    from app.models import HorizonProject

    project = db.query(HorizonProject).filter(HorizonProject.id == operation.project_id).first()
    if project is not None and (project.storage_root or 'data') != 'data':
        return
    project_dir = get_project_dir(operation.project_id)
    if project_dir.exists():
        if not project_dir.is_dir():
            raise RuntimeError('Project delete recovery target is not a folder')
        shutil.rmtree(project_dir)


def _apply_project_links_relocation(db: Session, operation: FileOperationJournal) -> str:
    from app.models import HorizonProject
    from app.services.projects import discard_staged_project_links, promote_staged_project_links

    try:
        payload = json.loads(operation.payload_json or '{}')
    except json.JSONDecodeError as exc:
        raise RuntimeError('Project-links relocation has invalid recovery metadata') from exc
    if not isinstance(payload, dict):
        raise RuntimeError('Project-links relocation has invalid recovery metadata')

    staged_name = payload.get('staged_name')
    staged_digest = payload.get('staged_digest')
    target = (payload.get('target_storage_root'), payload.get('target_storage_path'))
    original = (payload.get('original_storage_root'), payload.get('original_storage_path'))
    if not isinstance(staged_name, str) or not isinstance(staged_digest, str) or len(staged_digest) != 64:
        raise RuntimeError('Project-links relocation is missing recovery metadata')

    project = db.get(HorizonProject, operation.project_id)
    current = (project.storage_root, project.storage_path) if project is not None else None
    if current == target:
        promote_staged_project_links(operation.project_id, staged_name, staged_digest)
        return 'complete'

    # The database transaction never reached its destination, or a later
    # relocation superseded it. In either case the staged metadata must not
    # replace the links belonging to the currently configured project root.
    discard_staged_project_links(operation.project_id, staged_name)
    return 'cancelled' if current == original else 'superseded'


def _repair_database_side(db: Session, operation: FileOperationJournal) -> None:
    from app.models import HorizonProject, MediaAsset
    from app.services.horizons.content import register_horizon_project_file
    from app.services.horizons.projects import touch_horizon_project
    from app.services.media_assets import (
        cleanup_retired_media_asset,
        escape_like_path,
        get_media_asset_by_path,
        get_media_assets_under_prefix_for_scope,
        normalize_storage_scope,
        retire_media_asset,
        update_media_asset_path,
        update_media_assets_under_prefix,
    )
    from app.services.path_references import (
        rewrite_project_links_payload,
        rewrite_project_path_references,
    )
    from app.services.projects import load_project_links, save_project_links

    if operation.operation_type == 'move_file':
        destination_asset = get_media_asset_by_path(db, operation.project_id, operation.destination_path or '', storage_scope='project')
        if destination_asset is None:
            updated_asset = update_media_asset_path(
                db,
                operation.project_id,
                operation.source_path or '',
                operation.destination_path or '',
                storage_scope='project',
                commit=False,
            )
            if updated_asset is None:
                register_horizon_project_file(
                    db,
                    operation.project_id,
                    operation.destination_path or '',
                    commit=False,
                )
        rewrite_project_path_references(
            db,
            operation.project_id,
            operation.source_path or '',
            operation.destination_path or '',
            commit=False,
        )
        project_links = load_project_links(operation.project_id)
        rewritten_links, link_count = rewrite_project_links_payload(
            project_links,
            old_path=operation.source_path or '',
            new_path=operation.destination_path or '',
        )
        if link_count:
            save_project_links(operation.project_id, rewritten_links)
        touch_horizon_project(db, operation.project_id, commit=False)
    elif operation.operation_type == 'move_folder':
        destination_assets = get_media_assets_under_prefix_for_scope(
            db,
            operation.project_id,
            operation.destination_path or '',
            storage_scope='project',
        )
        if not destination_assets:
            update_media_assets_under_prefix(
                db,
                operation.project_id,
                operation.source_path or '',
                operation.destination_path or '',
                storage_scope='project',
                commit=False,
            )
        rewrite_project_path_references(
            db,
            operation.project_id,
            operation.source_path or '',
            operation.destination_path or '',
            moved_is_folder=True,
            commit=False,
        )
        project_links = load_project_links(operation.project_id)
        rewritten_links, link_count = rewrite_project_links_payload(
            project_links,
            old_path=operation.source_path or '',
            new_path=operation.destination_path or '',
        )
        if link_count:
            save_project_links(operation.project_id, rewritten_links)
        touch_horizon_project(db, operation.project_id, commit=False)
    elif operation.operation_type == 'delete_file':
        assets = (
            db.query(MediaAsset)
            .filter(MediaAsset.project_id == operation.project_id)
            .filter(MediaAsset.file_path == (operation.source_path or ''))
            .filter(MediaAsset.storage_scope == 'project')
            .all()
        )
        for asset in assets:
            retire_media_asset(db, asset, 'deleted')
            cleanup_retired_media_asset(db, asset)
        touch_horizon_project(db, operation.project_id)
    elif operation.operation_type == 'delete_folder':
        prefix = str(operation.source_path or '').strip().strip('/')
        like_prefix = f'{escape_like_path(prefix)}/%'
        assets = (
            db.query(MediaAsset)
            .filter(MediaAsset.project_id == operation.project_id)
            .filter(MediaAsset.storage_scope == normalize_storage_scope('project'))
            .filter((MediaAsset.file_path == prefix) | (MediaAsset.file_path.like(like_prefix, escape='\\')))
            .all()
        )
        for asset in assets:
            retire_media_asset(db, asset, 'deleted')
            cleanup_retired_media_asset(db, asset)
        touch_horizon_project(db, operation.project_id)
    elif operation.operation_type == 'delete_project':
        from app.services.horizons_fresh import DELETED_PROJECT_STATUS

        project = db.query(HorizonProject).filter(HorizonProject.id == operation.project_id).first()
        if project is not None:
            project.status = DELETED_PROJECT_STATUS
            project.visibility = 'private'
            project.updated_at = time.time()
            db.add(project)
        assets = db.query(MediaAsset).filter(MediaAsset.project_id == operation.project_id).all()
        for asset in assets:
            retire_media_asset(db, asset, 'project_deleted')
            cleanup_retired_media_asset(db, asset)
    db.flush()


def run_pending_file_operation_repairs() -> int:
    repaired = 0
    db = SessionLocal()
    try:
        operations = (
            db.query(FileOperationJournal)
            .filter(FileOperationJournal.status.in_(sorted(PENDING_STATUSES)))
            .order_by(FileOperationJournal.created_at.asc())
            .all()
        )
        for operation in operations:
            operation_id = operation.id
            operation.status = 'in_progress'
            operation.updated_at = time.time()
            db.add(operation)
            db.commit()
            try:
                if operation.operation_type in {'delete_file', 'delete_folder', 'delete_project'}:
                    _repair_database_side(db, operation)
                if operation.operation_type == 'move_file':
                    _apply_move(db, operation, is_folder=False)
                elif operation.operation_type == 'move_folder':
                    _apply_move(db, operation, is_folder=True)
                elif operation.operation_type == 'delete_file':
                    _apply_delete(db, operation, is_folder=False)
                elif operation.operation_type == 'delete_folder':
                    _apply_delete(db, operation, is_folder=True)
                elif operation.operation_type == 'delete_project':
                    _apply_project_delete(db, operation)
                elif operation.operation_type == 'relocate_project_links':
                    outcome = _apply_project_links_relocation(db, operation)
                    if outcome != 'complete':
                        cancel_file_operation(
                            db,
                            operation,
                            'Project relocation did not commit' if outcome == 'cancelled' else 'Project relocation was superseded',
                        )
                        repaired += 1
                        continue
                else:
                    raise RuntimeError(f'Unknown file operation type: {operation.operation_type}')
                if operation.operation_type in {'move_file', 'move_folder'}:
                    _repair_database_side(db, operation)
                complete_file_operation(db, operation)
                repaired += 1
            except Exception as exc:
                # A failed flush leaves the Session unusable until it is rolled
                # back. Mark only this operation for review, then continue so a
                # single damaged journal entry cannot block unrelated repairs.
                db.rollback()
                operation = db.get(FileOperationJournal, operation_id)
                if operation is None:
                    continue
                fail_file_operation(db, operation, exc)
        return repaired
    finally:
        db.close()
