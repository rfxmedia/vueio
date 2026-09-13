from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import FileOperationJournal, HorizonProject, MediaAsset, ShareLink, UploadSession
from app.config import get_settings
from app.services.file_operation_journal import complete_file_operation
from app.services.media_assets import GENERATED_STORAGE_SCOPES, file_matches_content_identity, media_asset_reference_clause
from app.services.media_relink import MediaRelinkMatcher, apply_media_match, contained_file, relocation_plan_id, require_reviewed_plan
from app.services.media_resolution import source_signature
from app.services.path_references import rewrite_project_links_payload, rewrite_project_path_references
from app.services.storage_capacity import ensure_path_capacity
from app.services.projects import (
    discard_staged_project_links,
    check_project_folder_assignment,
    load_project_links,
    lock_project_storage,
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


def _project_assets_for_relink(db: Session, project_id: str) -> list[MediaAsset]:
    referenced = media_asset_reference_clause(db)
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(~MediaAsset.storage_scope.in_(GENERATED_STORAGE_SCOPES))
        .filter(or_(MediaAsset.unavailable_at.is_(None), referenced))
        .filter(or_(MediaAsset.storage_scope != 'media_root', referenced))
        .order_by(MediaAsset.file_path.asc(), MediaAsset.created_at.desc())
        .all()
    )


def _asset_relative_candidates(asset: MediaAsset) -> list[str]:
    normalized = str(asset.file_path or '').strip().replace('\\', '/').strip('/')
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {'', '.', '..'} for part in parts):
        return []
    if asset.storage_scope != 'media_root':
        return [str(PurePosixPath(*parts))]
    return [str(PurePosixPath(*parts[index:])) for index in range(len(parts))]


def _project_path_changes(matched: list[dict]) -> dict[str, str]:
    destinations: dict[str, set[str]] = {}
    for item in matched:
        if item.get('source_scope') != 'media_root':
            destinations.setdefault(item['source_path'], set()).add(item['path'])
    # Historical versions can share an old filename. Their stable IDs remain
    # authoritative; a path-only reference must not pick one arbitrarily.
    return {source: next(iter(paths)) for source, paths in destinations.items()
            if len(paths) == 1 and source not in paths}


def _rebased_link_source(link: dict, matched: list[dict]) -> str | None:
    source = str(link.get('source_path') or '').strip().strip('/')
    if not source:
        return None
    for item in matched:
        if item.get('source_scope') != 'media_root':
            continue
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
        target = contained_file(destination, relative_path)
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
    path_changes = _project_path_changes(matched)
    if path_changes:
        links_data, rewritten = rewrite_project_links_payload(links_data, old_path=path_changes, new_path=None)
        changed = changed or bool(rewritten)
    return links_data if changed else None


def plan_project_relocation(db: Session, project: HorizonProject, storage_root: str, storage_path: str) -> dict:
    destination = check_project_folder_assignment(db, storage_root, storage_path, project_id=project.id)
    if not destination.exists() or not destination.is_dir():
        raise HTTPException(status_code=404, detail='Selected project folder does not exist')

    matched: list[dict] = []
    missing: list[dict] = []
    external_sources: list[dict] = []
    matcher = MediaRelinkMatcher(destination)
    for asset in _project_assets_for_relink(db, project.id):
        match, issue = matcher.match(asset, _asset_relative_candidates(asset))
        if match is not None:
            matched.append(match)
        elif issue is not None:
            if asset.storage_scope == 'media_root':
                original = contained_file(get_settings().MEDIA_ROOT, asset.file_path)
                if original is not None and original.is_file() and (
                    file_matches_content_identity(original, asset.content_hash)
                    or (not asset.content_hash and asset.source_signature == source_signature(original))
                ):
                    external_sources.append({'asset_id': asset.id, 'path': asset.file_path, 'signature': source_signature(original)})
                    continue
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
            original = contained_file(get_settings().MEDIA_ROOT, link.get('source_path'))
            expected_folder = str(link.get('type') or '').lower() in {'folder', 'directory'}
            if original is not None and (original.is_dir() if expected_folder else original.is_file()):
                continue
            link_missing.append(link_issue)

    matched_count = len(matched)
    total_count = matched_count + len(missing)
    link_matched_count = len(link_matches)
    link_total_count = link_matched_count + len(link_missing)
    plan = {
        'project_id': project.id,
        'root': storage_root,
        'path': storage_path,
        'matched': matched,
        'missing': missing,
        'retained': external_sources,
        'link_matches': link_matches,
        'link_missing': link_missing,
        'matched_count': matched_count,
        'missing_count': len(missing),
        'total_count': total_count,
        'link_matched_count': link_matched_count,
        'link_missing_count': len(link_missing),
        'link_total_count': link_total_count,
        'legacy_rebased_count': sum(1 for item in matched if item.get('legacy_rebased')),
        'read_only': storage_location_is_read_only(destination),
        'directory_identity': [destination.stat().st_dev, destination.stat().st_ino],
        'links_digest': hashlib.sha256(json.dumps(links_data, sort_keys=True).encode()).hexdigest(),
        'can_commit': (total_count == 0 and link_total_count == 0) or matched_count > 0 or link_matched_count > 0,
    }
    plan['plan_id'] = relocation_plan_id(project, plan)
    return plan


def commit_project_relocation(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
    *,
    revoke_shares: bool = False,
    expected_plan_id: str | None = None,
) -> dict:
    check_project_folder_assignment(db, storage_root, storage_path, project_id=project.id, lock=True)
    lock_project_storage(db, project)
    plan = plan_project_relocation(db, project, storage_root, storage_path)
    require_reviewed_plan(plan, expected_plan_id)
    if not plan['can_commit']:
        raise HTTPException(status_code=409, detail={'message': 'No tracked project files matched this folder', 'plan': plan})
    return commit_project_media_plan(db, project, plan, revoke_shares=revoke_shares)


def _require_idle_project_files(db: Session, project_id: str) -> None:
    pending_operation = (
        db.query(FileOperationJournal)
        .filter(FileOperationJournal.project_id == project_id)
        .filter(FileOperationJournal.status.in_(['pending', 'in_progress', 'manual_review']))
        .first()
    )
    if pending_operation is not None:
        raise HTTPException(status_code=409, detail='A file operation is still pending for this project. Finish or recover it before changing the folder.')
    if db.query(UploadSession.id).filter(
        or_(UploadSession.project_id == project_id,
            UploadSession.share_id.in_(db.query(ShareLink.id).filter(ShareLink.project_id == project_id))),
        UploadSession.status == 'active',
        or_(UploadSession.expires_at.is_(None), UploadSession.expires_at > time.time()),
    ).first():
        raise HTTPException(status_code=409, detail='This project has an active upload. Finish or cancel it before changing the folder.')


def commit_project_media_plan(db: Session, project: HorizonProject, plan: dict, *, update_folder: bool = True, revoke_shares: bool = False) -> dict:
    """Commit verified bindings and their path references in one transaction."""
    _require_idle_project_files(db, project.id)
    storage_root = plan['root'] if update_folder else project.storage_root or 'data'
    storage_path = plan['path'] if update_folder else project.storage_path or project.id
    destination = resolve_storage_location(storage_root, storage_path)
    matched_by_id = {item['asset_id']: item for item in plan['matched']}
    now = time.time()
    original_storage_root = project.storage_root
    original_storage_path = project.storage_path
    links_update = _rebased_project_links(project.id, plan['matched'], plan.get('link_matches', []))
    link_operation = None
    staged_links_name = None
    staged_links_digest = None
    if links_update is not None:
        staged_links_name, staged_links_digest = stage_project_links(project.id, links_update)
        try:
            link_operation = FileOperationJournal(
                id=str(uuid.uuid4()), operation_type='relocate_project_links',
                project_id=project.id, status='pending',
                payload_json=json.dumps({
                    'original_storage_root': original_storage_root,
                    'original_storage_path': original_storage_path,
                    'target_storage_root': storage_root,
                    'target_storage_path': storage_path,
                    'staged_name': staged_links_name,
                    'staged_digest': staged_links_digest,
                }),
            )
            db.add(link_operation)
        except Exception:
            discard_staged_project_links(project.id, staged_links_name)
            raise

    path_changes = _project_path_changes(plan['matched'])
    try:
        asset_ids = list(matched_by_id)
        if update_folder:
            asset_ids.extend(item['asset_id'] for item in plan['missing'])
        assets = db.query(MediaAsset).filter(MediaAsset.project_id == project.id, MediaAsset.id.in_(asset_ids)).with_for_update().all()
        if len(assets) != len(set(asset_ids)):
            raise HTTPException(status_code=409, detail='Project media changed during the check. Check the folder again.')
        # Release the old unique path bindings before applying the new map.
        # These changes are private to this transaction, including on rollback.
        for asset in assets:
            asset.unavailable_at = asset.unavailable_at or now
        db.flush()
        for asset in assets:
            match = matched_by_id.get(asset.id)
            if match is None:
                if asset.unavailable_reason is None:
                    asset.unavailable_reason = 'relink_missing'
                    asset.updated_at = now
                    db.add(asset)
                continue
            apply_media_match(asset, destination, match, now)
            db.add(asset)

        if path_changes:
            rewrite_project_path_references(db, project.id, path_changes, None, commit=False)

        if update_folder:
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
    except Exception as exc:
        db.rollback()
        if staged_links_name is not None:
            discard_staged_project_links(project.id, staged_links_name)
        if isinstance(exc, IntegrityError):
            raise HTTPException(status_code=409, detail='Another request registered one of these files. Nothing was relinked. Check the folder again.') from exc
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
        '.thumbnails' in relative_path.parts[:1]
        or (
            len(relative_path.parts) == 1
            and (
                relative_path.name in VUEIO_PROJECT_METADATA_FILENAMES
                or relative_path.name.endswith('.tracker.json')
            )
        )
    )


def plan_internal_storage_migration(db: Session, project: HorizonProject, storage_root: str, storage_path: str) -> dict:
    if (project.storage_root or 'data') != 'data':
        raise HTTPException(status_code=409, detail='Project already uses an external storage location')
    source = resolve_project_root(project)
    destination = check_project_folder_assignment(db, storage_root, storage_path, project_id=project.id)
    if destination.is_relative_to(source.resolve()) or source.resolve().is_relative_to(destination):
        raise HTTPException(status_code=409, detail='Choose a separate folder for the copy.')
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
            destination_file = contained_file(destination, relative)
            if destination_file is None:
                conflicts.append({'path': relative, 'reason': 'invalid_path'})
                continue
            size = source_file.stat().st_size
            if not destination_file.exists():
                copy_items.append({'path': relative, 'size': size, 'signature': source_signature(source_file)})
                continue
            if not destination_file.is_file() or destination_file.stat().st_size != size:
                conflicts.append({'path': relative, 'reason': 'different_file'})
                continue
            if _file_digest(source_file) == _file_digest(destination_file):
                adopted.append({'path': relative, 'size': size, 'signature': source_signature(source_file)})
            else:
                conflicts.append({'path': relative, 'reason': 'different_file'})
    plan = {
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
    plan['plan_id'] = relocation_plan_id(project, plan)
    return plan


def migrate_internal_project_storage(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
    *,
    progress: MigrationProgress | None = None,
    expected_plan_id: str | None = None,
) -> dict:
    check_project_folder_assignment(db, storage_root, storage_path, project_id=project.id, lock=True)
    lock_project_storage(db, project)
    _require_idle_project_files(db, project.id)
    plan = plan_internal_storage_migration(db, project, storage_root, storage_path)
    require_reviewed_plan(plan, expected_plan_id)
    if plan['conflicts']:
        raise HTTPException(status_code=409, detail={'message': 'Destination contains conflicting files', 'plan': plan})
    source = resolve_project_root(project)
    destination = resolve_storage_location(storage_root, storage_path)
    ensure_path_capacity(
        destination, minimum_free_bytes=get_settings().UPLOAD_MIN_FREE_BYTES,
        required_bytes=plan['copy_bytes'], unavailable_detail='Cannot check free space on this drive.',
        insufficient_detail='This drive does not have enough free space for the copy.',
    )
    destination.mkdir(parents=True, exist_ok=True)
    total = len(plan['copy_items'])
    copied_bytes = 0
    if progress:
        progress(0, total, copied_bytes)
    for index, item in enumerate(plan['copy_items'], start=1):
        source_file = source / item['path']
        destination_file = contained_file(destination, item['path'])
        if destination_file is None:
            raise HTTPException(status_code=409, detail=f'Invalid destination path during migration: {item["path"]}')
        if source_signature(source_file) != item['signature']:
            raise HTTPException(status_code=409, detail='A source file changed. Let the save finish, then check the folder again.')
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        created_identity = None
        try:
            with source_file.open('rb') as source_handle, destination_file.open('xb') as destination_handle:
                stat = os.fstat(destination_handle.fileno())
                created_identity = (stat.st_dev, stat.st_ino)
                shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
            if (source_signature(source_file) != item['signature']
                    or destination_file.stat().st_size != item['size']
                    or _file_digest(destination_file) != _file_digest(source_file)):
                raise HTTPException(status_code=409, detail='The copy could not be verified. The original project folder was kept.')
            shutil.copystat(source_file, destination_file)
        except FileExistsError:
            if destination_file.stat().st_size != source_file.stat().st_size or _file_digest(destination_file) != _file_digest(source_file):
                raise HTTPException(status_code=409, detail=f'File appeared at destination during migration: {item["path"]}')
        except Exception:
            # Remove only the incomplete file created by this copy attempt.
            # Originals and files that were already at the destination stay put.
            try:
                stat = destination_file.lstat()
                if created_identity == (stat.st_dev, stat.st_ino):
                    destination_file.unlink()
            except OSError:
                pass
            raise
        copied_bytes += int(item.get('size') or 0)
        if progress:
            progress(index, total, copied_bytes)

    relocation = commit_project_relocation(db, project, storage_root, storage_path)
    return {**plan, 'status': 'complete', 'old_path': str(source), 'relocation': relocation}


def _update_migration_job(job_id: str, **patch) -> None:
    with _migration_jobs_lock:
        current = _migration_jobs.get(job_id)
        if current is not None:
            current.update(patch, updated_at=time.time())


def start_project_migration(project_id: str, storage_root: str, storage_path: str, *, expected_plan_id: str | None = None) -> tuple[dict, bool]:
    with _migration_jobs_lock:
        for job in _migration_jobs.values():
            if job['project_id'] == project_id and job['status'] in {'queued', 'running'}:
                if (job['root'], job['path']) != (storage_root, storage_path):
                    raise HTTPException(status_code=409, detail='A copy to another folder is already running. Wait for it to finish.')
                return dict(job), False
        job_id = str(uuid.uuid4())
        job = {
            'job_id': job_id,
            'project_id': project_id,
            'root': storage_root,
            'path': storage_path,
            'expected_plan_id': expected_plan_id,
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

        result = migrate_internal_project_storage(db, project, job['root'], job['path'], progress=report, expected_plan_id=job.get('expected_plan_id'))
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
