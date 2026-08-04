from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import HorizonProject, MediaAsset
from app.services.auth import get_request_user
from app.services.file_metadata import build_file_metadata
from app.services.file_operation_journal import create_file_operation, complete_file_operation, fail_file_operation
from app.services.file_access import require_user_file_browser_read_access
from app.services.horizon_pages import (
    create_horizon_page,
    delete_horizon_page,
    get_horizon_page_by_ref,
    list_horizon_pages,
    serialize_horizon_page,
    update_horizon_page,
)
from app.services.horizons_fresh import (
    DELETED_PROJECT_STATUS,
    create_horizon_project,
    delete_horizon_project_file,
    delete_horizon_project_folder,
    ensure_horizon_project_runtime_dir,
    ensure_horizon_project_user_workspace,
    get_horizon_project,
    is_horizon_workspace_root_path,
    list_visible_horizon_project_summaries,
    move_horizon_project_file,
    move_horizon_project_folder,
    register_horizon_project_file,
    rename_horizon_project_file,
    rename_horizon_project_folder,
    require_horizon_user_workspace_path,
    require_horizon_project_access,
    serialize_horizon_project,
    touch_horizon_project,
    update_horizon_project,
)
from app.services.horizons.projects import list_unavailable_project_media
from app.services.media import get_safe_path
from app.services.media_assets import cleanup_retired_media_asset, register_media_asset, retire_media_asset
from app.services.media_resolution import resolve_project_content_target, resolve_project_link_target
from app.services.project_access import verify_path_in_project
from app.services.project_content_gateway import ContentRef, HorizonsProjectAuthPolicy, LegacyProjectAuthPolicy, build_metadata, list_content
from app.services.project_links import find_link_by_virtual_path, linked_virtual_root
from app.services.project_permissions import make_project_path_smb_mutable, make_project_tree_smb_mutable
from app.services.projects import get_project_dir, load_project_links, save_project_links
from app.services.recently_viewed import purge_recently_viewed_for_project
from app.services.search_index import invalidate_search_index
from app.services.share_access import build_project_file_info_payload
from app.services.trackers import queue_thumbnail_warmup_for_paths
from app.services.uploads import (
    AuthorizedUploadScope,
    UPLOAD_SCOPE_PROJECT,
    append_authorized_upload_chunk,
    cancel_authorized_upload_item,
    cancel_authorized_upload_session,
    create_authorized_upload_session,
    find_upload_item,
    get_authorized_upload_session,
    read_limited_upload_chunk,
    serialize_upload_patch_response,
    serialize_upload_session,
    validate_uploader_name,
    write_bounded_upload,
)

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(tags=['projects'])

MEDIA_ROOT = settings.MEDIA_ROOT
PDF_EXTENSIONS = {'.pdf'}
LINKED_FOLDER_UPLOAD_DISABLED_REASON = 'Uploads are disabled inside linked NAS folders. Upload into a project-owned folder or use Link from NAS.'


# Project browser permission model:
# - project root hosts high-level app objects (trackers/pages) plus real workspace folders
# - artist accounts always browse/mutate through their own real workspace folder, even with an editor grant
# - editor grants allow shot/version work and file management, not project-structure controls
def _is_workspace_scoped_artist(user: dict | None) -> bool:
    return bool(user and (user.get('role') or '').strip().lower() == 'artist')


def _is_project_artist(user: dict | None) -> bool:
    return _is_workspace_scoped_artist(user)


def _is_artist_user(user: dict | None) -> bool:
    return _is_workspace_scoped_artist(user)


def _role_can_edit_project_files(access_role: str | None) -> bool:
    return access_role in {'admin', 'owner', 'editor'}


def _normalize_project_rel_path(path: str | None) -> str:
    return str(path or '').strip().strip('/')


def _ensure_artist_workspace_project_path(db: Session, project_id: str, user: dict | None, path: str | None, *, allow_workspace_root: bool = True) -> str:
    return require_horizon_user_workspace_path(
        db,
        project_id,
        user,
        path,
        allow_workspace_root=allow_workspace_root,
    )


class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = ''
    due_date: Optional[str] = None
    thumbnail_path: Optional[str] = None
    status: Optional[str] = 'not_started'
    storage_root: Optional[str] = None
    storage_path: Optional[str] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    thumbnail_path: Optional[str] = None
    status: Optional[str] = None


class PageCreate(BaseModel):
    title: str
    description: Optional[str] = ''
    cover_path: Optional[str] = None
    blocks: Optional[list[dict]] = None


class PageUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_path: Optional[str] = None
    blocks: Optional[list[dict]] = None


class FolderCreate(BaseModel):
    name: str
    parent_path: Optional[str] = ''


class LinkFileRequest(BaseModel):
    source_path: str
    target_folder: Optional[str] = ''


class LinkFilesRequest(BaseModel):
    source_paths: list[str]
    target_folder: Optional[str] = ''


class DuplicateRequest(BaseModel):
    path: str
    type: str
    is_linked: bool = False
    target_folder: str = ''


class RenameRequest(BaseModel):
    new_name: str


class MoveRequest(BaseModel):
    target_folder: str


class UploadManifestItemRequest(BaseModel):
    rel_path: str
    original_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: int


class UploadSessionCreateRequest(BaseModel):
    uploader_name: str
    client_batch_id: str
    target_path: Optional[str] = ''
    files: list[UploadManifestItemRequest]


def _require_admin_user(vueio_session: str | None, x_vueio_agent_key: str | None) -> tuple[dict, str]:
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Admin access required')
    return user, auth_mode


def _require_project_access_ctx(
    db: Session,
    project_id: str,
    vueio_session: str | None,
    x_vueio_agent_key: str | None,
    *,
    required_role: str = 'viewer',
) -> tuple[dict, str, object, str]:
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role=required_role)
    return user, auth_mode, project, access_role


def _ensure_horizon_project_file_asset(db: Session, project_id: str, rel_path: str, existing_asset=None):
    return register_media_asset(db, project_id, rel_path, storage_scope='project')


def _build_project_file_info(project_id: str, path: str, *, db: Session | None = None) -> dict:
    file_path, _job_key, storage_scope = resolve_project_link_target(project_id, path)
    if file_path and file_path.exists():
        return build_project_file_info_payload(project_id, path, file_path, db=db, storage_scope=storage_scope)

    file_path, _job_key, _storage_scope = resolve_project_content_target(project_id, path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return build_file_metadata(file_path, path, db=db, project_id=project_id)


def _ensure_mutable_project_folder_path(path: str, *, detail: str = 'Workspace folders are protected') -> None:
    if is_horizon_workspace_root_path(path):
        raise HTTPException(status_code=400, detail=detail)


@router.get('/api/projects')
def list_projects(vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    projects = list_visible_horizon_project_summaries(db, user, auth_mode=auth_mode)
    projects.sort(key=lambda item: item.get('updated_at') or 0, reverse=True)
    return projects


@router.post('/api/projects')
def create_project(data: ProjectCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode = _require_admin_user(vueio_session, x_vueio_agent_key)

    project = create_horizon_project(
        db,
        title=data.title,
        description=data.description,
        due_date=data.due_date,
        thumbnail_path=data.thumbnail_path,
        status=data.status,
        created_by=user.get('id') or user.get('username'),
        storage_root=data.storage_root,
        storage_path=data.storage_path,
    )
    ensure_horizon_project_runtime_dir(db, project.id)
    return serialize_horizon_project(db, project, user=user)


@router.get('/api/projects/{project_id}')
def get_project(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    return serialize_horizon_project(db, project, user=user, access_role=access_role)


@router.get('/api/projects/{project_id}/offline-media')
def get_project_offline_media(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    _require_admin_user(vueio_session, x_vueio_agent_key)
    get_horizon_project(db, project_id)
    return list_unavailable_project_media(db, project_id)


@router.put('/api/projects/{project_id}')
def update_project(project_id: str, data: ProjectUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot update project settings')

    project = update_horizon_project(
        db,
        project_id,
        title=data.title,
        description=data.description,
        due_date=data.due_date,
        thumbnail_path=data.thumbnail_path,
        status=data.status,
        fields_set=set(data.model_fields_set),
    )
    return serialize_horizon_project(db, project, user=user)


@router.delete('/api/projects/{project_id}')
def delete_project(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    _require_admin_user(vueio_session, x_vueio_agent_key)

    project = db.query(HorizonProject).filter(HorizonProject.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail='Project not found')

    operation = create_file_operation(
        db,
        operation_type='delete_project',
        project_id=project_id,
        source_path='',
    )
    project_assets = db.query(MediaAsset).filter(MediaAsset.project_id == project_id).filter(MediaAsset.unavailable_at.is_(None)).all()
    for asset in project_assets:
        retire_media_asset(db, asset, 'project_deleted')

    project.status = DELETED_PROJECT_STATUS
    project.visibility = 'private'
    project.updated_at = time.time()
    db.add(project)
    purge_recently_viewed_for_project(db, project_id)
    db.commit()
    invalidate_search_index()
    for asset in project_assets:
        cleanup_retired_media_asset(db, asset)
    if project_assets:
        db.commit()

    project_dir = get_project_dir(project_id) if (project.storage_root or 'data') == 'data' else None
    try:
        if project_dir and project_dir.exists():
            shutil.rmtree(project_dir)
    except Exception:
        fail_file_operation(db, operation, RuntimeError('delete_project_failed'))
        raise
    complete_file_operation(db, operation)
    return {'status': 'deleted'}


@router.get('/api/projects/{project_id}/contents')
def list_project_contents(project_id: str, path: str = '', include_counts: bool = False, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    result = list_content(
        HorizonsProjectAuthPolicy(db, project_id, user, access_role),
        path,
        include_counts=include_counts,
    )
    return {
        'path': result.path,
        'items': result.items,
        'breadcrumbs': result.breadcrumbs,
        'folder_context': result.folder_context,
    }


@router.get('/api/projects/{project_id}/pages')
def list_project_pages(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    _user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    return {'pages': [serialize_horizon_page(db, page) for page in list_horizon_pages(db, project_id)]}


@router.post('/api/projects/{project_id}/pages')
def create_project_page(project_id: str, data: PageCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot create Vue pages')
    page = create_horizon_page(
        db,
        project_id,
        title=data.title,
        description=data.description,
        cover_path=data.cover_path,
        blocks=data.blocks,
        created_by=user.get('id') or user.get('username'),
    )
    touch_horizon_project(db, project_id)
    return serialize_horizon_page(db, page)


@router.get('/api/projects/{project_id}/pages/{page_ref}')
def get_project_page(project_id: str, page_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    _user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    page = get_horizon_page_by_ref(db, project_id, page_ref)
    return serialize_horizon_page(db, page)


@router.put('/api/projects/{project_id}/pages/{page_id}')
def update_project_page(project_id: str, page_id: str, data: PageUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot update Vue pages')
    page = update_horizon_page(
        db,
        project_id,
        page_id,
        title=data.title,
        description=data.description,
        cover_path=data.cover_path,
        blocks=data.blocks,
        fields_set=set(data.model_fields_set),
    )
    touch_horizon_project(db, project_id)
    return serialize_horizon_page(db, page)


@router.delete('/api/projects/{project_id}/pages/{page_id}')
def delete_project_page(project_id: str, page_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot delete Vue pages')
    delete_horizon_page(db, project_id, page_id)
    touch_horizon_project(db, project_id)
    return {'status': 'deleted'}


@router.post('/api/projects/{project_id}/folders')
def create_project_folder(project_id: str, data: FolderCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)

    safe_name = ''.join(c for c in data.name if c.isalnum() or c in ' -_').strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail='Invalid folder name')

    parent_path = (data.parent_path or '').strip().strip('/')
    if _is_artist_user(user):
        workspace_path = ensure_horizon_project_user_workspace(db, project_id, user)
        if not parent_path:
            parent_path = workspace_path
        if parent_path != workspace_path and not parent_path.startswith(f'{workspace_path}/'):
            raise HTTPException(status_code=403, detail='Artists can only create folders inside their workspace')
    elif not _role_can_edit_project_files(access_role):
        raise HTTPException(status_code=403, detail='Editor access required')

    parent = project_dir / parent_path if parent_path else project_dir
    new_folder = parent / safe_name
    verify_path_in_project(new_folder, project_dir)
    if new_folder.exists():
        raise HTTPException(status_code=400, detail='Folder already exists')
    new_folder.mkdir(parents=True)
    make_project_path_smb_mutable(new_folder)

    touch_horizon_project(db, project_id)
    return {'status': 'created', 'path': str(new_folder.relative_to(project_dir))}


@router.delete('/api/projects/{project_id}/folders')
def delete_project_folder(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    if _is_project_artist(user):
        path = _ensure_artist_workspace_project_path(db, project_id, user, path, allow_workspace_root=False)
    _ensure_mutable_project_folder_path(path)
    target = project_dir / path
    verify_path_in_project(target, project_dir)
    if not target.exists():
        raise HTTPException(status_code=404, detail='Folder not found')
    if not target.is_dir():
        raise HTTPException(status_code=400, detail='Not a folder')
    if target == project_dir:
        raise HTTPException(status_code=400, detail='Cannot delete project root')
    result = delete_horizon_project_folder(db, project_id, path)
    return {'status': 'deleted', **result}


def _resolve_project_upload_base_path(user: dict, access_role: str, project_id: str, target_path: str | None, db: Session) -> str:
    normalized_target_path = (target_path or '').strip().strip('/')
    if _is_artist_user(user):
        workspace_path = ensure_horizon_project_user_workspace(db, project_id, user)
        if not normalized_target_path:
            normalized_target_path = workspace_path
        if normalized_target_path != workspace_path and not normalized_target_path.startswith(f'{workspace_path}/'):
            raise HTTPException(status_code=403, detail='Artists can only upload into their workspace')
    elif not _role_can_edit_project_files(access_role):
        raise HTTPException(status_code=403, detail='Editor access required')
    return normalized_target_path


def _revalidate_project_upload_write_access(
    db: Session,
    *,
    project_id: str,
    user: dict,
    access_role: str,
    session,
) -> None:
    session_base_path = (session.base_path or '').strip().strip('/')
    allowed_base_path = _resolve_project_upload_base_path(
        user,
        access_role,
        project_id,
        session_base_path,
        db,
    )
    if allowed_base_path != session_base_path:
        raise HTTPException(status_code=403, detail='Upload target is no longer authorized')


@router.post('/api/projects/{project_id}/uploads')
def create_project_upload_session(
    project_id: str,
    data: UploadSessionCreateRequest,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    base_path = _resolve_project_upload_base_path(user, access_role, project_id, data.target_path, db)
    target_dir = project_dir / base_path if base_path else project_dir
    verify_path_in_project(target_dir, project_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(target_dir)
    if not os.access(target_dir, os.W_OK):
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server')

    upload_scope = AuthorizedUploadScope(
        scope_type=UPLOAD_SCOPE_PROJECT,
        root_dir=project_dir.resolve(),
        base_path=base_path,
        project_id=project_id,
        owner_user_id=user.get('id'),
    )
    session, items = create_authorized_upload_session(
        db,
        upload_scope,
        uploader_name=validate_uploader_name(data.uploader_name),
        client_batch_id=data.client_batch_id,
        manifest=[item.model_dump() for item in data.files],
    )
    return serialize_upload_session(session, items)


@router.get('/api/projects/{project_id}/uploads/{session_id}')
def get_project_upload_session(
    project_id: str,
    session_id: str,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_PROJECT, root_dir=ensure_horizon_project_runtime_dir(db, project_id).resolve(), base_path='', project_id=project_id, owner_user_id=user.get('id'))
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    return serialize_upload_session(session, items)


@router.patch('/api/projects/{project_id}/uploads/{session_id}/items/{item_id}')
async def patch_project_upload_item(
    project_id: str,
    session_id: str,
    item_id: str,
    request: Request,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    upload_offset: int = Header(..., alias='Upload-Offset'),
    db: Session = Depends(get_db),
):
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_PROJECT, root_dir=ensure_horizon_project_runtime_dir(db, project_id).resolve(), base_path='', project_id=project_id, owner_user_id=user.get('id'))
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    _revalidate_project_upload_write_access(
        db,
        project_id=project_id,
        user=user,
        access_role=access_role,
        session=session,
    )
    item = find_upload_item(items, item_id)
    chunk = await read_limited_upload_chunk(request)
    session, _items, item = append_authorized_upload_chunk(
        db,
        upload_scope,
        session=session,
        item=item,
        offset=upload_offset,
        chunk=chunk,
    )
    return serialize_upload_patch_response(session, item)


@router.delete('/api/projects/{project_id}/uploads/{session_id}/items/{item_id}')
def delete_project_upload_item(
    project_id: str,
    session_id: str,
    item_id: str,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_PROJECT, root_dir=ensure_horizon_project_runtime_dir(db, project_id).resolve(), base_path='', project_id=project_id, owner_user_id=user.get('id'))
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    item = find_upload_item(items, item_id)
    session, items = cancel_authorized_upload_item(db, upload_scope, session=session, item=item)
    return serialize_upload_session(session, items)


@router.delete('/api/projects/{project_id}/uploads/{session_id}')
def delete_project_upload_session(
    project_id: str,
    session_id: str,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_PROJECT, root_dir=ensure_horizon_project_runtime_dir(db, project_id).resolve(), base_path='', project_id=project_id, owner_user_id=user.get('id'))
    session, _items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    session, items = cancel_authorized_upload_session(db, upload_scope, session=session)
    return serialize_upload_session(session, items)


@router.post('/api/projects/{project_id}/import')
async def import_file_to_project(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), target_folder: str = Form(''), file: UploadFile = File(...), db: Session = Depends(get_db)):
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)

    normalized_target_folder = (target_folder or '').strip().strip('/')
    if _is_artist_user(user):
        workspace_path = ensure_horizon_project_user_workspace(db, project_id, user)
        if not normalized_target_folder:
            normalized_target_folder = workspace_path
        if normalized_target_folder != workspace_path and not normalized_target_folder.startswith(f'{workspace_path}/'):
            raise HTTPException(status_code=403, detail='Artists can only upload into their workspace')
    elif not _role_can_edit_project_files(access_role):
        raise HTTPException(status_code=403, detail='Editor access required')

    target_dir = project_dir / normalized_target_folder if normalized_target_folder else project_dir
    verify_path_in_project(target_dir, project_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(target_dir)

    safe_name = ''.join(c for c in (file.filename or '') if c.isalnum() or c in '.-_ ').strip()
    if not safe_name:
        safe_name = f'file_{int(time.time())}'

    base_name = Path(safe_name).stem
    extension = Path(safe_name).suffix
    temp_path = target_dir / f'.upload_{uuid.uuid4().hex}.tmp'
    file_size = 0
    try:
        file_size = await write_bounded_upload(file, temp_path, root_dir=project_dir)

        def build_dest(counter: int) -> Path:
            name = f'{base_name}{extension}' if counter == 0 else f'{base_name}_{counter}{extension}'
            return target_dir / name

        final_path = None
        counter = 0
        use_link = True
        while final_path is None:
            dest = build_dest(counter)
            if use_link:
                try:
                    os.link(temp_path, dest)
                    make_project_path_smb_mutable(dest)
                    final_path = dest
                    break
                except FileExistsError:
                    counter += 1
                    continue
                except OSError as exc:
                    if exc.errno in (errno.EXDEV, errno.EPERM, errno.EACCES, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL):
                        use_link = False
                        continue
                    raise
            else:
                try:
                    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    try:
                        os.replace(temp_path, dest)
                        make_project_path_smb_mutable(dest)
                    except Exception:
                        try:
                            os.unlink(dest)
                        except Exception:
                            pass
                        raise
                    final_path = dest
                    break
                except FileExistsError:
                    counter += 1
                    continue

        if temp_path.exists():
            temp_path.unlink()
    except HTTPException:
        if temp_path.exists():
            temp_path.unlink()
        raise
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        logger.error('Project file import failed (%s)', type(exc).__name__)
        raise HTTPException(status_code=500, detail='Upload failed')

    rel_path = str(final_path.relative_to(project_dir))
    try:
        register_horizon_project_file(db, project_id, rel_path, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        final_path.unlink(missing_ok=True)
        raise
    try:
        queue_thumbnail_warmup_for_paths([rel_path], db=db, project_id=project_id)
    except Exception:
        logger.exception('Could not queue thumbnail warmup for imported project file %s', rel_path)

    return {'status': 'imported', 'path': rel_path, 'name': final_path.name, 'size': file_size}


def _append_project_link(links_data: dict, source_path: str, target_folder: str | None) -> dict:
    normalized_source = str(source_path or '').strip()
    if not normalized_source:
        raise HTTPException(status_code=400, detail='Source path is required')

    source_fs = get_safe_path(normalized_source)
    if not source_fs.exists():
        raise HTTPException(status_code=404, detail='Source file not found')

    normalized_target = str(target_folder or '').strip('/')
    link_type = 'folder' if source_fs.is_dir() else 'file'
    for link in links_data.get('links', []):
        if (
            link.get('source_path') == normalized_source
            and (link.get('target_folder', '') or '').strip('/') == normalized_target
            and (link.get('type') or 'file') == link_type
        ):
            raise HTTPException(status_code=400, detail='Item already linked in this folder')

    link = {
        'source_path': normalized_source,
        'target_folder': normalized_target,
        'type': link_type,
        'storage_scope': 'media_root',
        'created_at': time.time(),
    }
    links_data.setdefault('links', []).append(link)
    return link


@router.post('/api/projects/{project_id}/link')
def link_nas_file(project_id: str, data: LinkFileRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot link NAS files to projects')
    ensure_horizon_project_runtime_dir(db, project_id)
    require_user_file_browser_read_access(user, data.source_path)
    links_data = load_project_links(project_id)
    link = _append_project_link(links_data, data.source_path, data.target_folder)
    save_project_links(project_id, links_data)
    touch_horizon_project(db, project_id)
    return {'status': 'linked', 'type': link['type']}


@router.post('/api/projects/{project_id}/links')
def link_nas_files(project_id: str, data: LinkFilesRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot link NAS files to projects')
    ensure_horizon_project_runtime_dir(db, project_id)

    source_paths = []
    seen = set()
    for raw_path in data.source_paths or []:
        source_path = str(raw_path or '').strip()
        if not source_path or source_path in seen:
            continue
        seen.add(source_path)
        source_paths.append(source_path)
    if not source_paths:
        raise HTTPException(status_code=400, detail='No files selected')

    for source_path in source_paths:
        require_user_file_browser_read_access(user, source_path)
    links_data = load_project_links(project_id)
    linked = [_append_project_link(links_data, source_path, data.target_folder) for source_path in source_paths]
    save_project_links(project_id, links_data)
    touch_horizon_project(db, project_id)
    return {'status': 'linked', 'count': len(linked), 'items': linked}


@router.delete('/api/projects/{project_id}/link')
def unlink_nas_file(project_id: str, source_path: str, target_folder: str = None, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot unlink NAS files from projects')
    ensure_horizon_project_runtime_dir(db, project_id)
    links_data = load_project_links(project_id)
    original_count = len(links_data.get('links', []))
    if target_folder is None:
        links_data['links'] = [link for link in links_data.get('links', []) if link.get('source_path') != source_path]
    else:
        tf = str(target_folder or '')
        links_data['links'] = [link for link in links_data.get('links', []) if not (link.get('source_path') == source_path and (link.get('target_folder', '') or '') == tf)]
    if len(links_data['links']) == original_count:
        raise HTTPException(status_code=404, detail='Link not found')
    save_project_links(project_id, links_data)

    touch_horizon_project(db, project_id)
    return {'status': 'unlinked'}


@router.delete('/api/projects/{project_id}/files')
def delete_project_file(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        path = _ensure_artist_workspace_project_path(db, project_id, user, path, allow_workspace_root=False)
    result = delete_horizon_project_file(db, project_id, path)
    return {'status': 'deleted', **result}


@router.post('/api/projects/{project_id}/duplicate')
def duplicate_project_item(project_id: str, data: DuplicateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        data.path = _ensure_artist_workspace_project_path(db, project_id, user, data.path, allow_workspace_root=False)
        data.target_folder = _ensure_artist_workspace_project_path(db, project_id, user, data.target_folder, allow_workspace_root=True)
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    normalized_target_folder = _normalize_project_rel_path(data.target_folder)
    target_dir = project_dir / normalized_target_folder if normalized_target_folder else project_dir
    verify_path_in_project(target_dir, project_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail='Target folder not found')

    def get_copy_name(base_name: str, extension: str = '', *, parent: Path = target_dir) -> str:
        counter = 1
        new_name = f'{base_name} copy'
        while (parent / (new_name + extension)).exists():
            counter += 1
            new_name = f'{base_name} copy {counter}'
        return new_name + extension

    def copy_file_without_overwrite(source: Path, destination: Path) -> None:
        try:
            descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail='Duplicate destination already exists') from exc
        try:
            with os.fdopen(descriptor, 'wb') as output, source.open('rb') as input_file:
                shutil.copyfileobj(input_file, output)
            shutil.copystat(source, destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    if data.type == 'folder':
        if data.is_linked:
            links = load_project_links(project_id)
            original_link = find_link_by_virtual_path(links.get('links', []), data.path)
            if not original_link:
                raise HTTPException(status_code=404, detail='Linked folder not found')
            links.setdefault('links', []).append({
                'source_path': original_link.get('source_path'),
                'target_folder': data.target_folder,
                'type': 'folder',
                'storage_scope': original_link.get('storage_scope', 'media_root'),
                'created_at': time.time(),
            })
            save_project_links(project_id, links)
        else:
            _ensure_mutable_project_folder_path(data.path)
            source = project_dir / data.path
            verify_path_in_project(source, project_dir)
            if not source.exists() or not source.is_dir():
                raise HTTPException(status_code=404, detail='Folder not found')
            new_name = get_copy_name(source.name)
            dest = target_dir / new_name
            shutil.copytree(source, dest)
            make_project_tree_smb_mutable(dest)
    elif data.type == 'tracker':
        tracker_path = data.path if data.path.endswith('.tracker.json') else f'{data.path}.tracker.json'
        source = project_dir / tracker_path
        verify_path_in_project(source, project_dir)
        if not source.exists() or not source.is_file():
            raise HTTPException(status_code=404, detail='Tracker not found')
        tracker_data = json.loads(source.read_text())
        base_name = source.stem.replace('.tracker', '')
        new_name = get_copy_name(base_name, '.tracker.json', parent=project_dir)
        tracker_data['name'] = new_name.replace('.tracker.json', '')
        dest = project_dir / new_name
        dest.write_text(json.dumps(tracker_data, indent=2))
        make_project_path_smb_mutable(dest)
    elif data.type == 'file':
        if data.is_linked:
            links = load_project_links(project_id)
            original_link = None
            for link in links.get('links', []):
                if link['source_path'] == data.path or link.get('target_folder', '') + '/' + Path(link['source_path']).name == data.path:
                    original_link = link
                    break
            if not original_link:
                raise HTTPException(status_code=404, detail='Linked file not found')
            links.setdefault('links', []).append({
                'source_path': original_link['source_path'],
                'target_folder': data.target_folder,
                'storage_scope': original_link.get('storage_scope', 'media_root'),
                'created_at': time.time(),
            })
            save_project_links(project_id, links)
        else:
            source = project_dir / data.path
            verify_path_in_project(source, project_dir)
            if not source.exists():
                raise HTTPException(status_code=404, detail='File not found')
            base = source.stem
            ext = source.suffix
            new_name = get_copy_name(base, ext)
            dest = target_dir / new_name
            copy_file_without_overwrite(source, dest)
            make_project_path_smb_mutable(dest)
    else:
        raise HTTPException(status_code=400, detail='Unknown item type')

    touch_horizon_project(db, project_id)
    return {'status': 'duplicated'}


@router.put('/api/projects/{project_id}/files/rename')
def rename_project_file(project_id: str, path: str, data: RenameRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        path = _ensure_artist_workspace_project_path(db, project_id, user, path, allow_workspace_root=False)
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    target = project_dir / path
    verify_path_in_project(target, project_dir)
    if not target.exists():
        raise HTTPException(status_code=404, detail='File not found')
    if target.name == 'project.json':
        raise HTTPException(status_code=400, detail='Cannot rename system files')
    if target.name.endswith('.tracker.json'):
        raise HTTPException(status_code=400, detail='Use tracker rename endpoint for trackers')
    if target.is_dir():
        _ensure_mutable_project_folder_path(path)

    if target.is_dir():
        result = rename_horizon_project_folder(db, project_id, path, new_name=data.new_name)
    else:
        new_name = data.new_name
        if target.suffix and not new_name.endswith(target.suffix):
            new_name += target.suffix
        result = rename_horizon_project_file(db, project_id, path, new_name=new_name)
    return {'status': 'renamed', 'new_path': result['path']}


@router.put('/api/projects/{project_id}/files/move')
def move_project_file(project_id: str, path: str, data: MoveRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        path = _ensure_artist_workspace_project_path(db, project_id, user, path, allow_workspace_root=False)
        data.target_folder = _ensure_artist_workspace_project_path(db, project_id, user, data.target_folder, allow_workspace_root=True)
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    links_data = load_project_links(project_id)
    links_list = links_data.get('links', []) or []
    for link in links_list:
        vroot = linked_virtual_root(link)
        if link.get('source_path') == path or vroot == (path or '').strip('/'):
            link['target_folder'] = data.target_folder or ''
            save_project_links(project_id, links_data)
            touch_horizon_project(db, project_id)
            return {'status': 'moved', 'new_path': linked_virtual_root(link)}

    source = project_dir / path
    verify_path_in_project(source, project_dir)
    if not source.exists():
        raise HTTPException(status_code=404, detail='Source not found')
    if source.name == 'project.json':
        raise HTTPException(status_code=400, detail='Cannot move system files')
    if source.name.endswith('.tracker.json'):
        raise HTTPException(status_code=400, detail='Cannot move trackers')
    if source.is_dir():
        _ensure_mutable_project_folder_path(path)

    target_dir = project_dir / data.target_folder if data.target_folder else project_dir
    verify_path_in_project(target_dir, project_dir)
    if not target_dir.exists():
        raise HTTPException(status_code=404, detail='Target folder not found')
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail='Target must be a folder')

    if source.is_dir():
        result = move_horizon_project_folder(db, project_id, path, target_folder=data.target_folder)
    else:
        result = move_horizon_project_file(db, project_id, path, target_folder=data.target_folder)
    return {'status': 'moved', 'new_path': result['path']}


@router.get('/api/projects/{project_id}/file-info')
def get_project_file_info(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    if db.query(HorizonProject).filter(HorizonProject.id == project_id).first():
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')
    user = require_project_auth(project_id, vueio_session)
    return build_metadata(LegacyProjectAuthPolicy(db, project_id, user, 'owner'), ContentRef(namespace='legacy_project', project_id=project_id, path=path))
