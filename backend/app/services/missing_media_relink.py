from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import HorizonProject, MediaAsset
from app.services.media_assets import file_matches_content_identity, unavailable_project_media_query
from app.services.media_relink import MediaRelinkMatcher, contained_file, relocation_plan_id, require_reviewed_plan
from app.services.media_resolution import source_signature
from app.services.project_relocation import commit_project_media_plan
from app.services.projects import lock_project_storage, resolve_project_root, resolve_storage_location


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


def _offline_assets(db: Session, project_id: str, project_root: Path) -> list[MediaAsset]:
    assets = (
        unavailable_project_media_query(db, project_id)
        .order_by(MediaAsset.file_path.asc(), MediaAsset.created_at.asc())
        .all()
    )
    # A file can move before anyone attempts playback. Inspect active bindings
    # during this explicit search, without changing records in a dry run.
    active = db.query(MediaAsset).filter(
        MediaAsset.project_id == project_id, MediaAsset.storage_scope == 'project',
        MediaAsset.unavailable_at.is_(None),
    ).order_by(MediaAsset.file_path.asc(), MediaAsset.created_at.asc()).all()
    for asset in active:
        target = contained_file(project_root, asset.file_path)
        try:
            if target is None or not target.is_file():
                assets.append(asset)
            elif asset.source_signature and source_signature(target) != asset.source_signature:
                if asset.content_hash and not file_matches_content_identity(target, asset.content_hash):
                    assets.append(asset)
        except OSError as exc:
            raise HTTPException(status_code=409, detail='A file could not be read. Check drive access, then try again.') from exc
    return assets


def plan_missing_media_relink(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
) -> dict:
    project_root, search_root = _search_root(project, storage_root, storage_path)
    matcher = MediaRelinkMatcher(project_root, search_root)
    matched: list[dict] = []
    missing: list[dict] = []
    for asset in _offline_assets(db, project.id, project_root):
        source_path = str(asset.file_path or '').replace('\\', '/').strip('/')
        match, issue = matcher.match(asset, [source_path])
        if match:
            matched.append(match)
        elif issue:
            missing.append(issue)

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
                .filter(MediaAsset.id.notin_([item['asset_id'] for item in matched]))
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
    plan = {
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
    plan['plan_id'] = relocation_plan_id(project, plan)
    return plan


def commit_missing_media_relink(
    db: Session,
    project: HorizonProject,
    storage_root: str,
    storage_path: str,
    *,
    expected_plan_id: str | None = None,
) -> dict:
    lock_project_storage(db, project)
    plan = plan_missing_media_relink(db, project, storage_root, storage_path)
    require_reviewed_plan(plan, expected_plan_id)
    if not plan['can_commit']:
        raise HTTPException(
            status_code=409,
            detail={'message': 'No missing media could be safely matched in this folder', 'plan': plan},
        )

    result = commit_project_media_plan(db, project, plan, update_folder=False)
    return {**result, 'relinked_count': plan['matched_count'], 'unresolved_count': plan['missing_count']}
