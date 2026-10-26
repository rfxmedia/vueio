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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import HorizonProject, HorizonTracker, MediaAsset
from app.services.auth import get_request_user
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
from app.services.media_assets import cleanup_retired_media_asset, retire_media_asset
from app.services.project_access import require_project_auth, verify_path_in_project
from app.services.project_content_gateway import ContentRef, HorizonsProjectAuthPolicy, LegacyProjectAuthPolicy, build_metadata, list_content
from app.services.project_links import find_link_by_virtual_path, linked_virtual_root
from app.services.project_permissions import make_project_path_smb_mutable, make_project_tree_smb_mutable
from app.services.projects import get_project_dir, load_project_links, save_project_links
from app.services.recently_viewed import purge_recently_viewed_for_project
from app.services.search_index import invalidate_search_index
from app.services.trackers import queue_thumbnail_warmup_for_paths
from app.services.uploads import (
    append_authorized_upload_chunk,
    cancel_authorized_upload_item,
    cancel_authorized_upload_session,
    create_project_upload_session as start_project_upload_session,
    find_upload_item,
    get_authorized_upload_session,
    project_upload_scope,
    read_limited_upload_chunk,
    resolve_project_upload_base_path,
    revalidate_project_upload_write_access,
    serialize_upload_patch_response,
    serialize_upload_session,
    write_bounded_upload,
)
from app.services.user_access import has_app_access, is_admin_user, is_restricted_project_member

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(tags=['projects'])

MEDIA_ROOT = settings.MEDIA_ROOT
PDF_EXTENSIONS = {'.pdf'}
LINKED_FOLDER_UPLOAD_DISABLED_REASON = 'Uploads are disabled inside linked storage folders. Upload into a project-owned folder or use Link from storage.'


# Project browser permission model:
# - project root hosts high-level app objects (trackers/pages) plus real workspace folders
# - review-only Member accounts browse/mutate through their own real workspace folder, even with an editor grant
# - editor grants allow shot/version work and file management, not project-structure controls
def _is_workspace_scoped_artist(user: dict | None) -> bool:
    return is_restricted_project_member(user)


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
    due_date: Optional[str] = Field(None, description='Date as YYYY-MM-DD.')
    thumbnail_path: Optional[str] = Field(None, description='A project file to use as the project thumbnail, relative to the project folder.')
    status: Optional[str] = Field('not_started', description='One of: active, on_hold, archived, not_started, in_progress, waiting_review, edits_requested, done.')
    storage_root: Optional[str] = Field(None, description="data (the default), the app's own storage, or a location id from list_storage_roots.")
    storage_path: Optional[str] = Field(None, description='The project folder in the storage location. Not used for data.')


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = Field(None, description='Date as YYYY-MM-DD.')
    thumbnail_path: Optional[str] = Field(None, description='A project file to use as the project thumbnail, relative to the project folder.')
    status: Optional[str] = Field(None, description='One of: active, on_hold, archived, not_started, in_progress, waiting_review, edits_requested, done.')


class PageCreate(BaseModel):
    title: str
    description: Optional[str] = ''
    cover_path: Optional[str] = Field(None, description='Cover image, relative to the project folder.')
    blocks: Optional[list[dict]] = Field(None, description='Page blocks. Each block has a type: text (body), tracker_list (tracker_ids: tracker ids or names), resource_list (resources: items with kind file, folder or url, a label, and a path or url) or upload_inbox (target_path relative to the project folder, description, enabled). Each block can have a title and hidden.')


class PageUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_path: Optional[str] = Field(None, description='Cover image, relative to the project folder.')
    blocks: Optional[list[dict]] = Field(None, description='Page blocks. Each block has a type: text (body), tracker_list (tracker_ids: tracker ids or names), resource_list (resources: items with kind file, folder or url, a label, and a path or url) or upload_inbox (target_path relative to the project folder, description, enabled). Each block can have a title and hidden. This list replaces all blocks.')


class FolderCreate(BaseModel):
    name: str
    parent_path: Optional[str] = Field('', description='Relative to the project folder. Empty for the root.')


class LinkFileRequest(BaseModel):
    source_path: str = Field(description='A path in shared storage, as listed by list_files.')
    target_folder: Optional[str] = Field('', description='Where the link shows, relative to the project folder. Empty for the root.')


class LinkFilesRequest(BaseModel):
    source_paths: list[str] = Field(description='Paths in shared storage, as listed by list_files.')
    target_folder: Optional[str] = Field('', description='Where the links show, relative to the project folder. Empty for the root.')


class DuplicateRequest(BaseModel):
    path: str = Field(description='The item, relative to the project folder.')
    type: str = Field(description='file, folder or tracker. tracker copies only old file-based trackers.')
    is_linked: bool = Field(False, description='True if the item is a link to shared storage.')
    target_folder: str = Field('', description='Folder for the copy, relative to the project folder. Empty for the root.')


class RenameRequest(BaseModel):
    new_name: str = Field(description='The new name. A file keeps its extension.')


class MoveRequest(BaseModel):
    target_folder: str = Field(description='Relative to the project folder. Empty for the root.')


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
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail='Admin access required')
    return user, auth_mode


def _require_app_capability_user(
    vueio_session: str | None,
    x_vueio_agent_key: str | None,
    capability: str,
    detail: str,
) -> tuple[dict, str]:
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    if not has_app_access(user, capability):
        raise HTTPException(status_code=403, detail=detail)
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


def _ensure_mutable_project_folder_path(path: str, *, detail: str = 'Workspace folders are protected') -> None:
    if is_horizon_workspace_root_path(path):
        raise HTTPException(status_code=400, detail=detail)


@router.get('/api/projects', summary='List projects', openapi_extra={'x-mcp-tool': 'projects_list'})
def list_projects(vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the projects this person can see, most recently updated first.

    Each project has its id, title, status, description, due date, counts of
    trackers, shots and versions, and this person's `access_role`.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    projects = list_visible_horizon_project_summaries(db, user, auth_mode=auth_mode)
    projects.sort(key=lambda item: item.get('updated_at') or 0, reverse=True)
    return projects


@router.post('/api/projects', summary='Create a project')
def create_project(data: ProjectCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create a project. This person becomes its owner.

    `storage_root` is `data`, the app's own storage, or a location id from
    list_storage_roots. For a location, `storage_path` is the project folder in
    it. If that folder exists, the project uses the files in it. If not, Vue.io
    creates the folder.
    """
    user, _auth_mode = _require_app_capability_user(
        vueio_session,
        x_vueio_agent_key,
        'create_projects',
        'Project creation access required',
    )

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
    return serialize_horizon_project(db, project, user=user)


@router.get('/api/projects/{project_id}', summary='Get a project')
def get_project(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get one project with its counts, storage state and this person's role.

    `has_offline_media` is true when project files are missing or the project
    storage is not available.
    """
    user, _auth_mode, project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    return serialize_horizon_project(db, project, user=user, access_role=access_role)


@router.get('/api/projects/{project_id}/offline-media', summary='List missing project media')
def get_project_offline_media(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the media files of a project that are missing or changed on disk.

    Each item has the file path, an `issue` (missing, changed or relink) and the
    shots and versions that use the file. The list has at most 100 files.
    `total` gives the full count. If the project storage is not available, the
    list is empty. Administrators only.
    """
    _require_admin_user(vueio_session, x_vueio_agent_key)
    get_horizon_project(db, project_id)
    return list_unavailable_project_media(db, project_id)


@router.put('/api/projects/{project_id}', summary='Update a project')
def update_project(project_id: str, data: ProjectUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change the title, description, due date, thumbnail or status of a project.

    Send only the fields to change.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')

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


@router.delete('/api/projects/{project_id}', summary='Delete a project')
def delete_project(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a project permanently. It cannot be restored.

    Its trackers, shots, versions and pages are no longer available. If the
    project uses the app's own storage, Vue.io deletes the project folder and
    all files in it. A project folder in another storage location stays on disk.
    """
    user, _auth_mode, _visible_project, _access_role = _require_project_access_ctx(
        db,
        project_id,
        vueio_session,
        x_vueio_agent_key,
        required_role='owner',
    )
    if not has_app_access(user, 'delete_projects'):
        raise HTTPException(status_code=403, detail='Project deletion access required')

    project = db.query(HorizonProject).filter(HorizonProject.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail='Project not found')

    operation = create_file_operation(
        db,
        operation_type='delete_project',
        project_id=project_id,
        source_path='',
    )
    # Tracker mutations lock one tracker and then touch the project. Lock every
    # tracker in a stable order before deleting the project so a concurrent
    # restore cannot resume halfway through deletion.
    db.query(HorizonTracker.id).filter(
        HorizonTracker.project_id == project_id,
    ).order_by(HorizonTracker.id.asc()).with_for_update().all()
    project = db.query(HorizonProject).filter(
        HorizonProject.id == project_id,
    ).populate_existing().with_for_update().first()
    if project is None:
        fail_file_operation(db, operation, RuntimeError('project_missing'))
        raise HTTPException(status_code=404, detail='Project not found')
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


@router.get('/api/projects/{project_id}/contents', summary='List project folder contents')
def list_project_contents(project_id: str, path: str = '', include_counts: bool = False, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the items in one folder of a project.

    `path` is a folder relative to the project folder. Leave it empty for the
    project root, which also lists the project's pages and trackers. Each item
    has a `type`: page, folder, tracker or file. `include_counts` adds the number
    of items in each folder.
    """
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


@router.get('/api/projects/{project_id}/pages', summary='List project pages')
def list_project_pages(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the pages of a project, oldest first, with their blocks."""
    _user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    return {'pages': [serialize_horizon_page(db, page) for page in list_horizon_pages(db, project_id)]}


@router.post('/api/projects/{project_id}/pages', summary='Create a project page')
def create_project_page(project_id: str, data: PageCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create a page in a project.

    A page has blocks of text, tracker lists, resource lists and an upload
    inbox. Without `blocks`, the page gets four default blocks: Overview,
    Trackers, Resources and Client Uploads. The slug comes from the title.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
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


@router.get('/api/projects/{project_id}/pages/{page_ref}', summary='Get a project page')
def get_project_page(project_id: str, page_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get one project page with its blocks.

    `page_ref` is the page id or slug. Tracker and resource blocks include the
    trackers and files they point to.
    """
    _user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    page = get_horizon_page_by_ref(db, project_id, page_ref)
    return serialize_horizon_page(db, page)


@router.put('/api/projects/{project_id}/pages/{page_id}', summary='Update a project page')
def update_project_page(project_id: str, page_id: str, data: PageUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change the title, description, cover or blocks of a project page.

    `page_id` is the page id or slug. Send only the fields to change. `blocks`
    replaces all blocks of the page. A new title also changes the slug.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
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


@router.delete('/api/projects/{project_id}/pages/{page_id}', summary='Delete a project page')
def delete_project_page(project_id: str, page_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a project page permanently.

    `page_id` is the page id or slug. Files that were uploaded through the page
    stay in the project.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
    delete_horizon_page(db, project_id, page_id)
    touch_horizon_project(db, project_id)
    return {'status': 'deleted'}


@router.post('/api/projects/{project_id}/folders', summary='Create a project folder')
def create_project_folder(project_id: str, data: FolderCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create a folder in a project.

    `parent_path` is relative to the project folder. Leave it empty for the
    root. Vue.io removes all characters from `name` except letters, digits,
    spaces, hyphens and underscores.
    """
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
            raise HTTPException(status_code=403, detail='Members with review access can only create folders inside their workspace')
    elif not _role_can_edit_project_files(access_role):
        raise HTTPException(status_code=403, detail='Editor access required')

    parent = project_dir / parent_path if parent_path else project_dir
    new_folder = parent / safe_name
    verify_path_in_project(new_folder, project_dir)
    if new_folder.exists():
        raise HTTPException(status_code=400, detail='Folder already exists')
    try:
        new_folder.mkdir(parents=True)
    except OSError as error:
        logger.warning('Could not create project folder %s: %s', new_folder, error.strerror or error)
        raise HTTPException(
            status_code=409,
            detail='The folder could not be created. Check that the storage location allows changes.',
        ) from error
    make_project_path_smb_mutable(new_folder)

    touch_horizon_project(db, project_id)
    return {'status': 'created', 'path': str(new_folder.relative_to(project_dir))}


@router.delete('/api/projects/{project_id}/folders', summary='Delete a project folder')
def delete_project_folder(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a project folder and all files in it from disk. This is permanent.

    `path` is relative to the project folder. Versions that use these files show
    them as missing. The workspace folders of team members cannot be deleted.
    """
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


@router.post('/api/projects/{project_id}/uploads', summary='Start a resumable project upload')
def create_project_upload_session(
    project_id: str,
    data: UploadSessionCreateRequest,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Start or resume an upload of files into a project folder.

    `target_path` is relative to the project folder. Members with review access
    upload only into their workspace, which is also their default. Send each
    file's bytes with patch_project_upload_item.
    """
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    session, items = start_project_upload_session(
        db,
        project_id=project_id,
        user=user,
        access_role=access_role,
        target_path=data.target_path,
        uploader_name=data.uploader_name,
        client_batch_id=data.client_batch_id,
        manifest=[item.model_dump() for item in data.files],
    )
    return serialize_upload_session(session, items)


@router.get('/api/projects/{project_id}/uploads/{session_id}', summary='Get a project upload')
def get_project_upload_session(
    project_id: str,
    session_id: str,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Get the progress of each file in one of your project uploads."""
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = project_upload_scope(db, project_id, user)
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    return serialize_upload_session(session, items)


@router.patch('/api/projects/{project_id}/uploads/{session_id}/items/{item_id}', summary='Send a chunk of a project upload')
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
    """Send the next raw chunk of one file, up to 8 MB.

    `Upload-Offset` is the number of bytes already sent. When the last chunk
    arrives, the file moves into the project folder.
    """
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = project_upload_scope(db, project_id, user)
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    revalidate_project_upload_write_access(
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


@router.delete('/api/projects/{project_id}/uploads/{session_id}/items/{item_id}', summary='Cancel one file of a project upload')
def delete_project_upload_item(
    project_id: str,
    session_id: str,
    item_id: str,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Cancel one file of a project upload. Files that are complete stay."""
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = project_upload_scope(db, project_id, user)
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    item = find_upload_item(items, item_id)
    session, items = cancel_authorized_upload_item(db, upload_scope, session=session, item=item)
    return serialize_upload_session(session, items)


@router.delete('/api/projects/{project_id}/uploads/{session_id}', summary='Cancel a project upload')
def delete_project_upload_session(
    project_id: str,
    session_id: str,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Cancel the files of a project upload that are not complete."""
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    upload_scope = project_upload_scope(db, project_id, user)
    session, _items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    session, items = cancel_authorized_upload_session(db, upload_scope, session=session)
    return serialize_upload_session(session, items)


@router.post('/api/projects/{project_id}/import', summary='Upload a file to a project')
async def import_file_to_project(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), target_folder: str = Form(''), file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload one file into a project folder.

    `target_folder` is relative to the project folder. Leave it empty for the
    root. If the file name is in use, Vue.io adds a number, for example
    `plate_1.exr`. Vue.io registers the file as a media asset.
    """
    user, _auth_mode, _project, access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='viewer')
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)

    normalized_target_folder = resolve_project_upload_base_path(db, project_id, user, access_role, target_folder)

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


@router.post('/api/projects/{project_id}/link', summary='Link a storage item')
def link_nas_file(project_id: str, data: LinkFileRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Show a file or folder from shared storage inside a project.

    `source_path` is a path in shared storage, as listed by list_files. Vue.io
    does not copy the item. The link shows in `target_folder`.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
    ensure_horizon_project_runtime_dir(db, project_id)
    require_user_file_browser_read_access(user, data.source_path)
    links_data = load_project_links(project_id)
    link = _append_project_link(links_data, data.source_path, data.target_folder)
    save_project_links(project_id, links_data)
    touch_horizon_project(db, project_id)
    return {'status': 'linked', 'type': link['type']}


@router.post('/api/projects/{project_id}/links', summary='Link several storage items')
def link_nas_files(project_id: str, data: LinkFilesRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Show several files or folders from shared storage inside a project.

    Each path in `source_paths` is a path in shared storage, as listed by
    list_files. Vue.io does not copy the items. If one item is already linked
    in `target_folder`, Vue.io links none of them.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
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


@router.delete('/api/projects/{project_id}/link', summary='Remove a storage link')
def unlink_nas_file(project_id: str, source_path: str, target_folder: str = None, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Remove a link to a shared storage item from a project.

    `source_path` is the linked path in shared storage. With `target_folder`,
    only the link in that folder is removed. Without it, the links in all
    folders are removed. The item in shared storage does not change.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
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


@router.delete('/api/projects/{project_id}/files', summary='Delete a project file')
def delete_project_file(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a file from a project and from disk. This is permanent.

    `path` is relative to the project folder. Versions that use the file show it
    as missing.
    """
    user, _auth_mode, _project, _access_role = _require_project_access_ctx(db, project_id, vueio_session, x_vueio_agent_key, required_role='editor')
    if _is_project_artist(user):
        path = _ensure_artist_workspace_project_path(db, project_id, user, path, allow_workspace_root=False)
    result = delete_horizon_project_file(db, project_id, path)
    return {'status': 'deleted', **result}


@router.post('/api/projects/{project_id}/duplicate', summary='Duplicate a project item')
def duplicate_project_item(project_id: str, data: DuplicateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Copy a file or folder in a project. The copy has "copy" in its name.

    `path` and `target_folder` are relative to the project folder. For a link to
    shared storage, set `is_linked`. Vue.io then adds a second link and does not
    copy the files.
    """
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


@router.put('/api/projects/{project_id}/files/rename', summary='Rename a project file or folder')
def rename_project_file(project_id: str, path: str, data: RenameRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Rename a file or folder in a project.

    `path` is relative to the project folder. A file keeps its extension. Links
    to the item in pages, comments and shares change to the new path. Trackers
    cannot be renamed here.
    """
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


@router.put('/api/projects/{project_id}/files/move', summary='Move a project file or folder')
def move_project_file(project_id: str, path: str, data: MoveRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Move a file or folder to another folder in the same project.

    `path` and `target_folder` are relative to the project folder. Use an empty
    `target_folder` for the root. For a link to shared storage, only the link
    moves. Links in pages, comments and shares change to the new path.
    """
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


@router.get('/api/projects/{project_id}/file-info', deprecated=True, summary='Get legacy project file info')
def get_project_file_info(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get file details for an old file-based project.

    Current projects return a 409 error. For them, use
    get_horizons_media_asset_file_info or get_horizons_shot_version_file_info.
    """
    if db.query(HorizonProject).filter(HorizonProject.id == project_id).first():
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')
    user = require_project_auth(project_id, vueio_session)
    return build_metadata(LegacyProjectAuthPolicy(db, project_id, user, 'owner'), ContentRef(namespace='legacy_project', project_id=project_id, path=path))
