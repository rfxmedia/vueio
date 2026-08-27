from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import HorizonProject, MediaAsset
from app.services.media_assets import (
    GENERATED_STORAGE_SCOPES,
    content_fingerprint,
    file_matches_content_identity,
)
from app.services.media_resolution import source_signature, stored_media_asset_cache_identity
from app.services.path_references import rewrite_project_path_references
from app.services.projects import resolve_project_root, resolve_storage_location


def _search_root(project: HorizonProject, storage_root: str, storage_path: str) -> tuple[Path, Path]:
    project_storage_root = str(project.storage_root or 'data').strip().lower()
    if storage_root != project_storage_root:
        raise HTTPException(
            status_code=409,
            detail='Missing media can only be searched for inside the current working project folder',
        )
    project_root = resolve_project_root(project).resolve()
    search_root = resolve_storage_location(storage_root, storage_path).resolve()
    try:
        search_root.relative_to(project_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail='Choose the project folder or one of its subfolders',
        ) from exc
    if not search_root.exists() or not search_root.is_dir():
        raise HTTPException(status_code=404, detail='Selected search folder does not exist')
    return project_root, search_root


def _offline_assets(db: Session, project_id: str) -> list[MediaAsset]:
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.unavailable_at.isnot(None))
        .filter(MediaAsset.unavailable_reason != 'duplicate_active_generation')
        .order_by(MediaAsset.file_path.asc(), MediaAsset.created_at.asc())
        .all()
    )


def _identity_size(asset: MediaAsset) -> int:
    size = int(asset.file_size or 0)
    if size:
        return size
    parts = str(asset.content_hash or '').split(':', 2)
    if len(parts) == 3 and parts[0] == 'sampled-sha256-v1':
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0


def _files_by_size(project_root: Path, search_root: Path) -> dict[int, list[tuple[Path, str]]]:
    candidates: dict[int, list[tuple[Path, str]]] = {}
    for directory, subdirectories, filenames in os.walk(search_root, followlinks=False):
        directory_path = Path(directory)
        subdirectories[:] = sorted(
            name for name in subdirectories
            if not (directory_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            candidate = directory_path / filename
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                relative_path = resolved.relative_to(project_root).as_posix()
                size = resolved.stat().st_size
            except (OSError, ValueError):
                continue
            candidates.setdefault(size, []).append((resolved, relative_path))
    return candidates


def plan_missing_media_relink(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
) -> dict:
    project_root, search_root = _search_root(project, storage_root, storage_path)
    files_by_size = _files_by_size(project_root, search_root)
    matched: list[dict] = []
    missing: list[dict] = []

    for asset in _offline_assets(db, project.id):
        source_path = str(asset.file_path or '').strip().replace('\\', '/').strip('/')
        if asset.storage_scope in GENERATED_STORAGE_SCOPES:
            missing.append({
                'asset_id': asset.id,
                'path': source_path,
                'reason': 'generated_media',
            })
            continue

        expected_size = _identity_size(asset)
        if not expected_size:
            missing.append({
                'asset_id': asset.id,
                'path': source_path,
                'reason': 'identity_unavailable',
            })
            continue

        identity = str(asset.content_hash or '').strip()
        identity_matches: list[tuple[Path, str]] = []
        for candidate, relative_path in files_by_size.get(expected_size, []):
            if identity:
                if file_matches_content_identity(candidate, identity):
                    identity_matches.append((candidate, relative_path))
            elif relative_path == source_path:
                # The exact registered location plus its stored size is the
                # only safe recovery option for older assets without a hash.
                identity_matches.append((candidate, relative_path))

        if len(identity_matches) == 1:
            _candidate, relative_path = identity_matches[0]
            matched.append({
                'asset_id': asset.id,
                'path': relative_path,
                'source_path': source_path,
                'size': expected_size,
            })
        elif len(identity_matches) > 1:
            missing.append({
                'asset_id': asset.id,
                'path': source_path,
                'reason': 'ambiguous_match',
                'candidates': [relative_path for _candidate, relative_path in identity_matches],
            })
        else:
            missing.append({
                'asset_id': asset.id,
                'path': source_path,
                'reason': 'not_found',
            })

    matches_by_path: dict[str, list[dict]] = {}
    for item in matched:
        matches_by_path.setdefault(item['path'], []).append(item)
    colliding_ids = {
        item['asset_id']
        for items in matches_by_path.values()
        if len(items) > 1
        for item in items
    }

    matched_paths = [item['path'] for item in matched if item['asset_id'] not in colliding_ids]
    registered_paths = set()
    if matched_paths:
        registered_paths = {
            asset.file_path
            for asset in (
                db.query(MediaAsset)
                .filter(MediaAsset.project_id == project.id)
                .filter(MediaAsset.storage_scope == 'project')
                .filter(MediaAsset.unavailable_at.is_(None))
                .filter(MediaAsset.file_path.in_(matched_paths))
                .all()
            )
        }

    retained: list[dict] = []
    for item in matched:
        reason = None
        if item['asset_id'] in colliding_ids:
            reason = 'destination_already_matched'
        elif item['path'] in registered_paths:
            reason = 'destination_already_registered'
        if reason:
            missing.append({
                'asset_id': item['asset_id'],
                'path': item['source_path'],
                'reason': reason,
                'candidate': item['path'],
            })
        else:
            retained.append(item)
    matched = retained

    total_count = len(matched) + len(missing)
    return {
        'project_id': project.id,
        'root': storage_root,
        'path': storage_path,
        'matched': matched,
        'missing': missing,
        'matched_count': len(matched),
        'missing_count': len(missing),
        'total_count': total_count,
        'can_commit': bool(matched),
    }


def commit_missing_media_relink(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
) -> dict:
    plan = plan_missing_media_relink(db, project, storage_root, storage_path)
    if not plan['can_commit']:
        raise HTTPException(
            status_code=409,
            detail={'message': 'No missing media could be safely matched in this folder', 'plan': plan},
        )

    project_root = resolve_project_root(project).resolve()
    now = time.time()
    try:
        for item in plan['matched']:
            asset = db.get(MediaAsset, item['asset_id'])
            if asset is None or asset.unavailable_at is None:
                raise HTTPException(status_code=409, detail='Missing media changed while the search was being reviewed; search again')

            target = (project_root / item['path']).resolve()
            try:
                target.relative_to(project_root)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail='A matched file moved outside the project folder') from exc
            if not target.is_file() or target.is_symlink():
                raise HTTPException(status_code=409, detail='A matched file moved while the search was being reviewed; search again')

            signature_before = source_signature(target)
            stat = target.stat()
            if stat.st_size != int(item['size']) or (
                asset.content_hash
                and not file_matches_content_identity(target, asset.content_hash)
            ):
                raise HTTPException(status_code=409, detail='A matched file changed while the search was being reviewed; search again')
            verified_content_hash = asset.content_hash or content_fingerprint(target)
            signature_after = source_signature(target)
            stat = target.stat()
            if (
                verified_content_hash is None
                or signature_before != signature_after
                or stat.st_size != int(item['size'])
            ):
                raise HTTPException(status_code=409, detail='A matched file changed while the search was being reviewed; search again')

            collision = (
                db.query(MediaAsset.id)
                .filter(MediaAsset.project_id == project.id)
                .filter(MediaAsset.storage_scope == 'project')
                .filter(MediaAsset.file_path == item['path'])
                .filter(MediaAsset.unavailable_at.is_(None))
                .filter(MediaAsset.id != asset.id)
                .first()
            )
            if collision is not None:
                raise HTTPException(status_code=409, detail='A matched path is already registered to other media; search again')

            old_path = str(asset.file_path or '').strip().strip('/')
            old_scope = str(asset.storage_scope or '').strip().lower()
            if not asset.artifact_identity:
                asset.artifact_identity = stored_media_asset_cache_identity(asset)
            asset.file_path = item['path']
            asset.storage_scope = 'project'
            asset.source_signature = signature_after
            asset.content_hash = verified_content_hash
            asset.file_size = stat.st_size
            asset.modified_at = stat.st_mtime
            asset.unavailable_at = None
            asset.unavailable_reason = None
            asset.updated_at = now
            db.add(asset)
            if old_scope != 'media_root':
                rewrite_project_path_references(
                    db,
                    project.id,
                    old_path,
                    item['path'],
                    commit=False,
                )

        project.updated_at = now
        db.add(project)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        **plan,
        'committed': True,
        'relinked_count': plan['matched_count'],
        'unresolved_count': plan['missing_count'],
    }
