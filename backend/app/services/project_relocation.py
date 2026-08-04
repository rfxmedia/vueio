from __future__ import annotations

import hashlib
import shutil
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Comment, FileOperationJournal, HorizonProject, HorizonShot, HorizonShotVersion, MediaAsset, ShareLink
from app.services.file_operation_journal import cancel_file_operation, complete_file_operation, create_file_operation
from app.services.media_assets import GENERATED_STORAGE_SCOPES, content_fingerprint, file_matches_content_identity
from app.services.media_resolution import source_signature, stored_media_asset_cache_identity
from app.services.projects import (
    discard_staged_project_links,
    load_project_links,
    promote_staged_project_links,
    resolve_project_root,
    resolve_storage_location,
    stage_project_links,
    storage_location_is_read_only,
)

MigrationProgress = Callable[[int, int, int], None]
_migration_jobs: dict[str, dict] = {}
_migration_jobs_lock = threading.Lock()
VUEIO_PROJECT_METADATA_FILENAMES = {
    '.horizons-entity-thumbnails.json',
    '.links.json',
    'project.json',
}


def _asset_target(destination: Path, file_path: str | None) -> Path | None:
    """Return a contained, non-symlink-escaped destination for an asset."""
    destination = destination.resolve()
    try:
        target = (destination / str(file_path or '').strip().lstrip('/')).resolve(strict=False)
        target.relative_to(destination)
    except (OSError, RuntimeError, ValueError):
        return None
    return target


def _project_asset_ids_in_use(db: Session, project_id: str) -> set[str]:
    ids = {
        value
        for (value,) in db.query(HorizonShot.latest_media_asset_id)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShot.latest_media_asset_id.isnot(None))
    }
    ids.update(
        value
        for (value,) in db.query(HorizonShotVersion.media_asset_id)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.media_asset_id.isnot(None))
    )
    ids.update(
        value
        for (value,) in db.query(Comment.horizons_media_asset_id)
        .filter(Comment.project_id == project_id)
        .filter(Comment.horizons_media_asset_id.isnot(None))
    )
    return ids


def _project_assets_for_relink(db: Session, project_id: str) -> list[MediaAsset]:
    referenced_ids = _project_asset_ids_in_use(db, project_id)
    query = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(~MediaAsset.storage_scope.in_(GENERATED_STORAGE_SCOPES))
    )
    if referenced_ids:
        query = query.filter(or_(MediaAsset.unavailable_at.is_(None), MediaAsset.id.in_(referenced_ids)))
        query = query.filter(or_(MediaAsset.storage_scope != 'media_root', MediaAsset.id.in_(referenced_ids)))
    else:
        query = query.filter(MediaAsset.unavailable_at.is_(None), MediaAsset.storage_scope != 'media_root')
    return query.order_by(MediaAsset.file_path.asc(), MediaAsset.created_at.desc()).all()


def _asset_relative_candidates(asset: MediaAsset) -> list[str]:
    normalized = str(asset.file_path or '').strip().replace('\\', '/').strip('/')
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {'', '.', '..'} for part in parts):
        return []
    if asset.storage_scope != 'media_root':
        return [str(PurePosixPath(*parts))]
    return [str(PurePosixPath(*parts[index:])) for index in range(len(parts))]


def _match_asset_at_destination(destination: Path, asset: MediaAsset) -> tuple[dict | None, dict | None]:
    expected_size = int(asset.file_size or 0)
    candidates = _asset_relative_candidates(asset)
    existing: list[tuple[str, int]] = []
    matching: list[tuple[str, int]] = []
    for relative_path in candidates:
        target = _asset_target(destination, relative_path)
        if target is None or not target.exists() or not target.is_file():
            continue
        actual_size = target.stat().st_size
        existing.append((relative_path, actual_size))
        if expected_size and actual_size != expected_size:
            continue
        if asset.content_hash and not file_matches_content_identity(target, asset.content_hash):
            continue
        matching.append((relative_path, actual_size))
        # An exact relative path is authoritative once its content identity
        # matches. Looser suffix candidates are only for legacy media-root
        # paths whose old top-level hierarchy is no longer present.
        if relative_path == str(asset.file_path or '').strip().replace('\\', '/').strip('/'):
            matching = [(relative_path, actual_size)]
            break

    if len(matching) == 1:
        relative_path, actual_size = matching[0]
        return {
            'asset_id': asset.id,
            'path': relative_path,
            'source_path': asset.file_path,
            'size': actual_size,
            'legacy_rebased': asset.storage_scope == 'media_root' and relative_path != asset.file_path,
        }, None
    if len(matching) > 1:
        return None, {
            'asset_id': asset.id,
            'path': asset.file_path,
            'source_path': asset.file_path,
            'reason': 'ambiguous_match',
            'candidates': [path for path, _size in matching],
        }
    if existing:
        relative_path, actual_size = existing[0]
        return None, {
            'asset_id': asset.id,
            'path': relative_path,
            'source_path': asset.file_path,
            'reason': 'content_mismatch' if asset.content_hash and (not expected_size or expected_size == actual_size) else 'size_mismatch',
            'expected_size': expected_size,
            'actual_size': actual_size,
        }
    return None, {
        'asset_id': asset.id,
        'path': asset.file_path,
        'source_path': asset.file_path,
        'reason': 'not_found' if candidates else 'invalid_path',
    }


def _rebased_link_source(link: dict, matched: list[dict]) -> str | None:
    source = str(link.get('source_path') or '').strip().strip('/')
    if not source:
        return None
    for item in matched:
        old_path = str(item.get('source_path') or '').strip().strip('/')
        new_path = str(item.get('path') or '').strip().strip('/')
        suffix = old_path[len(source):].lstrip('/') if old_path == source or old_path.startswith(f'{source}/') else None
        if suffix is None or (suffix and not new_path.endswith(f'/{suffix}')):
            continue
        return new_path[:-(len(suffix) + 1)] if suffix else new_path
    return None


def _link_relative_candidates(link: dict) -> list[str]:
    normalized = str(link.get('source_path') or '').strip().replace('\\', '/').strip('/')
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {'', '.', '..'} for part in parts):
        return []
    return [str(PurePosixPath(*parts[index:])) for index in range(len(parts))]


def _match_link_at_destination(destination: Path, index: int, link: dict) -> tuple[dict | None, dict | None]:
    candidates = _link_relative_candidates(link)
    expected_folder = str(link.get('type') or '').strip().lower() in {'folder', 'directory'}
    matching: list[str] = []
    source = str(link.get('source_path') or '').strip().replace('\\', '/').strip('/')
    for relative_path in candidates:
        target = _asset_target(destination, relative_path)
        if target is None or not target.exists():
            continue
        if (expected_folder and not target.is_dir()) or (not expected_folder and not target.is_file()):
            continue
        matching.append(relative_path)
        if relative_path == source:
            matching = [relative_path]
            break
    if len(matching) == 1:
        return {
            'link_index': index,
            'source_path': link.get('source_path'),
            'path': matching[0],
            'legacy_rebased': matching[0] != source,
        }, None
    return None, {
        'link_index': index,
        'source_path': link.get('source_path'),
        'reason': 'ambiguous_match' if matching else 'not_found',
        **({'candidates': matching} if matching else {}),
    }


def _rebased_project_links(project_id: str, matched: list[dict], link_matches: list[dict]) -> dict | None:
    links_data = load_project_links(project_id)
    changed = False
    direct_matches = {int(item['link_index']): item for item in link_matches}
    for index, link in enumerate(links_data.get('links', [])):
        if link.get('storage_scope', 'media_root') != 'media_root':
            continue
        new_source = _rebased_link_source(link, matched)
        if new_source is None and index in direct_matches:
            new_source = str(direct_matches[index].get('path') or '').strip().strip('/')
        if new_source:
            link['source_path'] = new_source
            link['storage_scope'] = 'project'
            changed = True
    return links_data if changed else None


def plan_project_relocation(db: Session, project: HorizonProject, storage_root: str, storage_path: str) -> dict:
    destination = resolve_storage_location(storage_root, storage_path)
    if not destination.exists() or not destination.is_dir():
        raise HTTPException(status_code=404, detail='Selected project folder does not exist')

    matched: list[dict] = []
    missing: list[dict] = []
    for asset in _project_assets_for_relink(db, project.id):
        match, issue = _match_asset_at_destination(destination, asset)
        if match is not None:
            matched.append(match)
        elif issue is not None:
            missing.append(issue)

    # A destination file may satisfy at most one asset identity. Reject every
    # collision instead of allowing iteration order to decide which records
    # silently inherit the same physical file.
    matches_by_path: dict[str, list[dict]] = {}
    for item in matched:
        matches_by_path.setdefault(str(item['path']), []).append(item)
    colliding_ids = {
        item['asset_id']
        for items in matches_by_path.values()
        if len(items) > 1
        for item in items
    }
    if colliding_ids:
        retained: list[dict] = []
        for item in matched:
            if item['asset_id'] not in colliding_ids:
                retained.append(item)
                continue
            missing.append({
                'asset_id': item['asset_id'],
                'path': item['path'],
                'source_path': item['source_path'],
                'reason': 'destination_already_matched',
            })
        matched = retained

    links_data = load_project_links(project.id)
    link_matches: list[dict] = []
    link_missing: list[dict] = []
    for index, link in enumerate(links_data.get('links', [])):
        if link.get('storage_scope', 'media_root') != 'media_root':
            continue
        if _rebased_link_source(link, matched) is not None:
            continue
        link_match, link_issue = _match_link_at_destination(destination, index, link)
        if link_match is not None:
            link_matches.append(link_match)
        elif link_issue is not None:
            link_missing.append(link_issue)

    matched_count = len(matched)
    total_count = matched_count + len(missing)
    link_matched_count = len(link_matches)
    link_total_count = link_matched_count + len(link_missing)
    return {
        'project_id': project.id,
        'root': storage_root,
        'path': storage_path,
        'matched': matched,
        'missing': missing,
        'link_matches': link_matches,
        'link_missing': link_missing,
        'matched_count': matched_count,
        'missing_count': len(missing),
        'total_count': total_count,
        'link_matched_count': link_matched_count,
        'link_missing_count': len(link_missing),
        'link_total_count': link_total_count,
        'legacy_rebased_count': sum(1 for item in matched if item.get('legacy_rebased')),
        'can_commit': (total_count > 0 and matched_count > 0) or (link_total_count > 0 and link_matched_count > 0),
    }


def commit_project_relocation(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
    *,
    revoke_shares: bool = False,
    allow_empty: bool = False,
) -> dict:
    plan = plan_project_relocation(db, project, storage_root, storage_path)
    if not plan['can_commit'] and not allow_empty:
        raise HTTPException(status_code=409, detail={'message': 'No tracked project files matched this folder', 'plan': plan})
    pending_link_relocation = (
        db.query(FileOperationJournal)
        .filter(FileOperationJournal.project_id == project.id)
        .filter(FileOperationJournal.operation_type == 'relocate_project_links')
        .filter(FileOperationJournal.status.in_(['pending', 'in_progress', 'manual_review']))
        .first()
    )
    if pending_link_relocation is not None:
        raise HTTPException(status_code=409, detail='A previous project relocation still needs recovery')

    destination = resolve_storage_location(storage_root, storage_path)
    matched_by_id = {item['asset_id']: item for item in plan['matched']}
    now = time.time()
    original_storage_root = project.storage_root
    original_storage_path = project.storage_path
    links_update = _rebased_project_links(project.id, plan['matched'], plan['link_matches'])
    link_operation = None
    staged_links_name = None
    staged_links_digest = None
    if links_update is not None:
        staged_links_name, staged_links_digest = stage_project_links(project.id, links_update)
        try:
            link_operation = create_file_operation(
                db,
                operation_type='relocate_project_links',
                project_id=project.id,
                payload={
                    'original_storage_root': original_storage_root,
                    'original_storage_path': original_storage_path,
                    'target_storage_root': storage_root,
                    'target_storage_path': storage_path,
                    'staged_name': staged_links_name,
                    'staged_digest': staged_links_digest,
                },
            )
        except Exception:
            discard_staged_project_links(project.id, staged_links_name)
            raise

    try:
        for asset in _project_assets_for_relink(db, project.id):
            match = matched_by_id.get(asset.id)
            if match is None:
                if asset.unavailable_at is None:
                    asset.unavailable_at = now
                    asset.unavailable_reason = 'relink_missing'
                    asset.updated_at = now
                    db.add(asset)
                continue
            target = _asset_target(destination, match['path'])
            if target is None:
                continue
            signature_before = source_signature(target)
            stat = target.stat()
            if stat.st_size != int(match.get('size') or 0) or (
                asset.content_hash
                and not file_matches_content_identity(target, asset.content_hash)
            ):
                raise HTTPException(
                    status_code=409,
                    detail='A destination file changed while the relocation was being verified; review the plan and retry',
                )
            verified_content_hash = asset.content_hash or content_fingerprint(target)
            signature_after = source_signature(target)
            stat = target.stat()
            if (
                verified_content_hash is None
                or signature_before != signature_after
                or stat.st_size != int(match.get('size') or 0)
            ):
                raise HTTPException(
                    status_code=409,
                    detail='A destination file changed while the relocation was being verified; review the plan and retry',
                )
            if not asset.artifact_identity:
                asset.artifact_identity = stored_media_asset_cache_identity(asset)
            if asset.storage_scope == 'media_root':
                asset.file_path = match['path']
                asset.storage_scope = 'project'
            asset.source_signature = signature_after
            asset.content_hash = verified_content_hash
            asset.file_size = stat.st_size
            asset.modified_at = stat.st_mtime
            asset.unavailable_at = None
            asset.unavailable_reason = None
            asset.updated_at = now
            db.add(asset)

        project.storage_root = storage_root
        project.storage_path = storage_path
        project.updated_at = now
        if revoke_shares:
            db.query(ShareLink).filter(ShareLink.project_id == project.id).filter(ShareLink.is_active.isnot(False)).update(
                {ShareLink.is_active: False},
                synchronize_session=False,
            )
        db.add(project)
        db.commit()
    except Exception:
        db.rollback()
        if staged_links_name is not None:
            discard_staged_project_links(project.id, staged_links_name)
        if link_operation is not None:
            operation = db.get(FileOperationJournal, link_operation.id)
            if operation is not None:
                cancel_file_operation(db, operation, 'Project relocation database update did not commit')
        raise

    db.refresh(project)
    if link_operation is not None and staged_links_name is not None and staged_links_digest is not None:
        try:
            promote_staged_project_links(project.id, staged_links_name, staged_links_digest)
        except Exception as exc:
            operation = db.get(FileOperationJournal, link_operation.id)
            if operation is not None:
                operation.error_text = f'Project links promotion pending: {exc}'
                operation.updated_at = time.time()
                db.add(operation)
                db.commit()
            raise
        operation = db.get(FileOperationJournal, link_operation.id)
        if operation is not None:
            complete_file_operation(db, operation)
    return {**plan, 'committed': True, 'revoked_shares': revoke_shares}


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _is_vueio_project_metadata(relative_path: Path) -> bool:
    """Return whether an internal-project file belongs to Vueio, not the user."""
    return (
        len(relative_path.parts) == 1
        and (
            relative_path.name in VUEIO_PROJECT_METADATA_FILENAMES
            or relative_path.name.endswith('.tracker.json')
        )
    )


def plan_internal_storage_migration(db: Session, project: HorizonProject, storage_root: str, storage_path: str) -> dict:
    if (project.storage_root or 'data') != 'data':
        raise HTTPException(status_code=409, detail='Project already uses an external storage location')
    source = resolve_project_root(project)
    destination = resolve_storage_location(storage_root, storage_path)
    if storage_location_is_read_only(destination):
        raise HTTPException(status_code=409, detail='Selected storage location is read-only')
    copy_items: list[dict] = []
    adopted: list[dict] = []
    conflicts: list[dict] = []
    if source.exists():
        source_root = source.resolve()
        for source_file in sorted(path for path in source.rglob('*') if path.is_file() and not path.is_symlink()):
            try:
                source_file.resolve().relative_to(source_root)
            except (OSError, RuntimeError, ValueError):
                continue
            relative_path = source_file.relative_to(source)
            if _is_vueio_project_metadata(relative_path):
                continue
            relative = str(relative_path)
            destination_file = _asset_target(destination, relative)
            if destination_file is None:
                conflicts.append({'path': relative, 'reason': 'invalid_path'})
                continue
            size = source_file.stat().st_size
            if not destination_file.exists():
                copy_items.append({'path': relative, 'size': size})
                continue
            if not destination_file.is_file() or destination_file.stat().st_size != size:
                conflicts.append({'path': relative, 'reason': 'different_file'})
                continue
            if _file_digest(source_file) == _file_digest(destination_file):
                adopted.append({'path': relative, 'size': size})
            else:
                conflicts.append({'path': relative, 'reason': 'different_file'})
    return {
        'project_id': project.id,
        'root': storage_root,
        'path': storage_path,
        'source_path': str(source),
        'copy_items': copy_items,
        'adopted': adopted,
        'conflicts': conflicts,
        'copy_count': len(copy_items),
        'adopted_count': len(adopted),
        'conflict_count': len(conflicts),
        'copy_bytes': sum(item['size'] for item in copy_items),
    }


def migrate_internal_project_storage(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
    *,
    progress: MigrationProgress | None = None,
) -> dict:
    plan = plan_internal_storage_migration(db, project, storage_root, storage_path)
    if plan['conflicts']:
        raise HTTPException(status_code=409, detail={'message': 'Destination contains conflicting files', 'plan': plan})
    source = resolve_project_root(project)
    destination = resolve_storage_location(storage_root, storage_path)
    destination.mkdir(parents=True, exist_ok=True)
    total = len(plan['copy_items'])
    copied_bytes = 0
    if progress:
        progress(0, total, copied_bytes)
    for index, item in enumerate(plan['copy_items'], start=1):
        source_file = source / item['path']
        destination_file = _asset_target(destination, item['path'])
        if destination_file is None:
            raise HTTPException(status_code=409, detail=f'Invalid destination path during migration: {item["path"]}')
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source_file.open('rb') as source_handle, destination_file.open('xb') as destination_handle:
                shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)
            shutil.copystat(source_file, destination_file)
        except FileExistsError:
            if destination_file.stat().st_size != source_file.stat().st_size or _file_digest(destination_file) != _file_digest(source_file):
                raise HTTPException(status_code=409, detail=f'File appeared at destination during migration: {item["path"]}')
        if destination_file.stat().st_size != source_file.stat().st_size or _file_digest(destination_file) != _file_digest(source_file):
            raise HTTPException(status_code=500, detail=f'Copied file failed verification: {item["path"]}')
        copied_bytes += int(item.get('size') or 0)
        if progress:
            progress(index, total, copied_bytes)

    relocation = commit_project_relocation(db, project, storage_root, storage_path, allow_empty=True)
    return {**plan, 'status': 'complete', 'old_path': str(source), 'relocation': relocation}


def _update_migration_job(job_id: str, **patch) -> None:
    with _migration_jobs_lock:
        current = _migration_jobs.get(job_id)
        if current is not None:
            current.update(patch, updated_at=time.time())


def start_project_migration(project_id: str, storage_root: str, storage_path: str) -> tuple[dict, bool]:
    with _migration_jobs_lock:
        for job in _migration_jobs.values():
            if job['project_id'] == project_id and job['status'] in {'queued', 'running'}:
                return dict(job), False
        job_id = str(uuid.uuid4())
        job = {
            'job_id': job_id,
            'project_id': project_id,
            'root': storage_root,
            'path': storage_path,
            'status': 'queued',
            'completed_files': 0,
            'total_files': 0,
            'copied_bytes': 0,
            'created_at': time.time(),
            'updated_at': time.time(),
        }
        _migration_jobs[job_id] = job
        if len(_migration_jobs) > 100:
            finished = sorted(
                (item for item in _migration_jobs.values() if item['status'] in {'complete', 'error'}),
                key=lambda item: item['updated_at'],
            )
            for item in finished[:len(_migration_jobs) - 100]:
                _migration_jobs.pop(item['job_id'], None)
        return dict(job), True


def run_project_migration(job_id: str) -> None:
    from app.db import SessionLocal

    with _migration_jobs_lock:
        job = dict(_migration_jobs.get(job_id) or {})
    if not job:
        return
    _update_migration_job(job_id, status='running')
    db = SessionLocal()
    try:
        project = db.query(HorizonProject).filter(HorizonProject.id == job['project_id']).first()
        if project is None:
            raise HTTPException(status_code=404, detail='Horizons project not found')

        def report(completed_files: int, total_files: int, copied_bytes: int) -> None:
            _update_migration_job(
                job_id,
                completed_files=completed_files,
                total_files=total_files,
                copied_bytes=copied_bytes,
            )

        result = migrate_internal_project_storage(db, project, job['root'], job['path'], progress=report)
        _update_migration_job(job_id, status='complete', result=result)
    except Exception as exc:
        db.rollback()
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        _update_migration_job(job_id, status='error', error=detail)
    finally:
        db.close()


def get_project_migration_job(project_id: str, job_id: str) -> dict:
    with _migration_jobs_lock:
        job = _migration_jobs.get(job_id)
        if job is None or job['project_id'] != project_id:
            raise HTTPException(status_code=404, detail='Project migration job not found')
        return dict(job)
