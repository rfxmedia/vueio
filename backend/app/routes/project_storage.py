from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth import require_admin, require_auth
from app.services.horizons.projects import get_horizon_project, serialize_horizon_project
from app.services.missing_media_relink import commit_missing_media_relink, plan_missing_media_relink
from app.services.project_relocation import (
    commit_project_relocation,
    get_project_migration_job,
    plan_internal_storage_migration,
    plan_project_relocation,
    run_project_migration,
    start_project_migration,
)
from app.services.projects import (
    configured_project_storage_catalog,
    configured_project_storage_roots,
    normalize_project_storage_path,
    resolve_storage_location,
    storage_location_is_read_only,
    storage_root_is_available,
)
from app.services.user_access import has_app_access

router = APIRouter(tags=['project-storage'])


def _require_project_creator(vueio_session: str | None) -> dict:
    user = require_auth(vueio_session)
    if not has_app_access(user, 'create_projects'):
        raise HTTPException(status_code=403, detail='Project creation access required')
    return user


class StorageFolderCreate(BaseModel):
    root: str
    path: str = ''
    name: str


class ProjectRelocateRequest(BaseModel):
    root: str
    path: str
    dry_run: bool = True
    revoke_shares: bool = False


class ProjectMigrateStorageRequest(BaseModel):
    root: str = 'projects'
    path: str
    dry_run: bool = True


class MissingMediaRelinkRequest(BaseModel):
    root: str
    path: str
    dry_run: bool = True


def _root_payload(name: str, item: dict) -> dict:
    path = item['path']
    return {
        'id': name,
        'label': item['label'],
        'read_only': storage_location_is_read_only(path),
        'available': storage_root_is_available(item),
    }


@router.get('/api/storage/roots')
def list_storage_roots(vueio_session: str = Cookie(None)):
    _require_project_creator(vueio_session)
    return [_root_payload(name, item) for name, item in configured_project_storage_catalog().items()]


@router.get('/api/storage/browse')
def browse_storage(root: str, path: str = '', vueio_session: str = Cookie(None)):
    _require_project_creator(vueio_session)
    root = root.strip().lower()
    normalized = normalize_project_storage_path(path, allow_empty=True)
    if normalized:
        target = resolve_storage_location(root, normalized)
    else:
        item = configured_project_storage_catalog().get(root)
        if item is None:
            raise HTTPException(status_code=409, detail='Selected storage location is not configured')
        if not storage_root_is_available(item):
            raise HTTPException(
                status_code=409,
                detail='Selected storage location is unavailable or its mounted filesystem changed',
            )
        target = item['path'].resolve()
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail='Folder not found')
    base = configured_project_storage_roots()[root].resolve()
    folders = []
    for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        if entry.is_dir() and not entry.name.startswith('.'):
            folders.append({'name': entry.name, 'path': str(entry.relative_to(base))})
    return {'root': root, 'path': normalized, 'read_only': storage_location_is_read_only(target), 'folders': folders}


@router.post('/api/storage/folders')
def create_storage_folder(data: StorageFolderCreate, vueio_session: str = Cookie(None)):
    _require_project_creator(vueio_session)
    root = data.root.strip().lower()
    configured_roots = configured_project_storage_roots()
    if root == 'data' or root not in configured_roots:
        raise HTTPException(status_code=409, detail='Selected storage location is not configured')
    if not configured_roots[root].is_dir():
        raise HTTPException(status_code=409, detail='Selected storage location is unavailable')
    safe_name = ''.join(character for character in data.name.strip() if character not in '/\\').strip(' .')
    if not safe_name:
        raise HTTPException(status_code=400, detail='Folder name is required')
    parent = normalize_project_storage_path(data.path, allow_empty=True)
    relative = '/'.join(part for part in (parent, safe_name) if part)
    target = resolve_storage_location(root, relative)
    if storage_location_is_read_only(target):
        raise HTTPException(status_code=409, detail='Selected storage location is read-only')
    if target.exists():
        raise HTTPException(status_code=409, detail='Folder already exists')
    target.mkdir(parents=True)
    return {'root': root, 'path': relative, 'name': safe_name}


@router.post('/api/projects/{project_id}/relocate')
def relocate_project(project_id: str, data: ProjectRelocateRequest, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    user = require_admin(vueio_session)
    project = get_horizon_project(db, project_id)
    root = data.root.strip().lower()
    normalized = normalize_project_storage_path(data.path)
    result = plan_project_relocation(db, project, root, normalized) if data.dry_run else commit_project_relocation(
        db,
        project,
        root,
        normalized,
        revoke_shares=data.revoke_shares,
    )
    return {**result, 'project': serialize_horizon_project(db, project, user=user)}


@router.post('/api/projects/{project_id}/relink-media')
def relink_missing_project_media(project_id: str, data: MissingMediaRelinkRequest, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    user = require_admin(vueio_session)
    project = get_horizon_project(db, project_id)
    root = data.root.strip().lower()
    normalized = normalize_project_storage_path(data.path)
    result = plan_missing_media_relink(db, project, root, normalized) if data.dry_run else commit_missing_media_relink(
        db,
        project,
        root,
        normalized,
    )
    return {**result, 'project': serialize_horizon_project(db, project, user=user)}


@router.post('/api/projects/{project_id}/migrate-storage')
def migrate_project_storage(project_id: str, data: ProjectMigrateStorageRequest, background_tasks: BackgroundTasks, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    user = require_admin(vueio_session)
    project = get_horizon_project(db, project_id)
    root = data.root.strip().lower()
    normalized = normalize_project_storage_path(data.path)
    if data.dry_run:
        result = plan_internal_storage_migration(db, project, root, normalized)
        return {**result, 'project': serialize_horizon_project(db, project, user=user)}
    job, is_new = start_project_migration(project.id, root, normalized)
    if is_new:
        background_tasks.add_task(run_project_migration, job['job_id'])
    return job


@router.get('/api/projects/{project_id}/migrate-storage/status')
def project_storage_migration_status(project_id: str, job_id: str, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    user = require_admin(vueio_session)
    project = get_horizon_project(db, project_id)
    job = get_project_migration_job(project_id, job_id)
    if job['status'] == 'complete':
        job['project'] = serialize_horizon_project(db, project, user=user)
    return job
