from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Form, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.limiter import client_rate_limit_key, enforce_rate_limit
from app.models import ShareLink
from app.services.auth import get_user_from_session, require_admin
from app.services.download_audit import create_download_event
from app.services.horizons_fresh import (
    compute_horizon_tracker_stats,
    get_horizon_media_asset_by_path,
    get_horizon_project,
    get_horizon_shot_by_ref,
    get_horizon_tracker_by_ref,
    get_horizon_tracker_for_share,
    list_horizon_trackers,
    list_visible_horizon_media_assets,
    tracker_settings_for,
    tracker_tool_enabled_for_context,
    refresh_horizon_tracker_stats_cache,
    require_horizon_project_access,
    serialize_horizon_project,
    serialize_horizon_tracker_detail,
)
from app.services.horizon_pages import (
    get_horizon_page_by_ref,
    get_page_upload_targets,
    page_allows_tracker,
    page_allows_upload_target,
    serialize_horizon_page,
)
from app.services.horizons.version_publication import (
    held_media_asset_ids_for_project,
    held_media_paths_for_project,
    latest_published_at_for_tracker,
    published_scope_summary,
    published_shot_ids_for_tracker,
    published_version_ids_for_tracker,
    published_versions,
)
from app.services.media_resolution import resolve_project_link_target
from app.services.media import get_safe_path
from app.services.media_assets import get_media_asset_by_path, register_media_asset
from app.services.project_content_gateway import SharedPagePolicy, SharedProjectFolderPolicy, SharedProjectPolicy, list_content
from app.services.project_links import find_link_target, join_rel_path, link_storage_scope
from app.services.project_access import verify_path_in_project
from app.services.project_delivery import build_delivery_logo_response
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.projects import get_project_dir, load_project_links, resolve_project_root
from app.services.share_access import create_share_link_with_retry, get_shared_content_info_dict, hash_share_password, issue_share_access_token, normalize_virtual_path, require_path_within_shared_root, validate_share
from app.services.share_management import apply_share_management_update, serialize_share_for_management
from app.services.tracker_downloads import build_tracker_latest_versions_zip, start_tracker_latest_versions_zip_job
from app.services.tracker_events import build_tracker_event_actor, list_tracker_activity
from app.services.tracker_views import TrackerViewRequest, record_tracker_view
from app.services.shot_commands import ShotCommandActor, ShotCommandContext, ShotCommandService
from app.services.uploads import (
    AuthorizedUploadScope,
    UPLOAD_SCOPE_SHARED,
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
)

settings = get_settings()
router = APIRouter(tags=['shares'])

MEDIA_ROOT = settings.MEDIA_ROOT
PDF_EXTENSIONS = {'.pdf'}
HIDDEN_FOLDERS = settings.hidden_storage_folders
SHOT_STATUSES = ['not_started', 'in_progress', 'waiting_review', 'edits_requested', 'done']


def _normalize_share_path(path: str | None) -> str:
    return normalize_virtual_path(path, allow_empty=True)


def _horizons_virtual_folder_exists(project_id: str, path: str, db: Session) -> bool:
    normalized_path = _normalize_share_path(path)
    if not normalized_path:
        return False
    prefix = f'{normalized_path}/'
    return any(
        _normalize_share_path(asset.file_path).startswith(prefix)
        for asset in list_visible_horizon_media_assets(db, project_id)
        if getattr(asset, 'file_path', None) and getattr(asset, 'storage_scope', None) != 'media_root'
    )


class ShareCreateRequest(BaseModel):
    path: str
    expires_at: Optional[float] = None
    password: Optional[str] = ''
    allow_download: bool = False
    allow_upload: bool = False
    request_files: bool = False


class ProjectShareCreateRequest(BaseModel):
    expires_at: Optional[float] = None
    password: Optional[str] = ''
    allow_download: bool = False
    tracker_id: Optional[str] = None
    tracker_name: Optional[str] = None
    page_id: Optional[str] = None


class ProjectContentShareRequest(BaseModel):
    path: str
    is_folder: bool = False
    expires_at: Optional[float] = None
    password: Optional[str] = ''
    allow_download: bool = False
    allow_upload: bool = False
    request_files: bool = False


class ProjectShareUpdateRequest(BaseModel):
    expires_at: Optional[float] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    allow_download: Optional[bool] = None
    allow_upload: Optional[bool] = None


class SharedShotStatusUpdate(BaseModel):
    status: str


class SharedTrackerLatestDownloadRequest(BaseModel):
    shot_ids: list[str] | None = None
    filename: str | None = None


class ShareUnlockRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


async def _read_share_unlock_request(request: Request) -> ShareUnlockRequest:
    content_length = request.headers.get('content-length')
    if content_length and content_length.isdigit() and int(content_length) > 4096:
        raise HTTPException(status_code=413, detail='Share unlock request is too large')
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(status_code=413, detail='Share unlock request is too large')
    content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    try:
        if content_type == 'application/json':
            payload = json.loads(body or b'{}')
        elif content_type == 'application/x-www-form-urlencoded':
            payload = {key: values[-1] for key, values in parse_qs(body.decode()).items() if values}
        else:
            raise HTTPException(status_code=415, detail='Use a JSON or form body')
        return ShareUnlockRequest.model_validate(payload)
    except HTTPException:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail='A valid password is required') from exc


def _parse_shared_tracker_download_form_shot_ids(raw: str | None) -> list[str] | None:
    value = (raw or '').strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [part.strip() for part in value.replace('\n', ',').split(',') if part.strip()]


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



def _serialize_share_created(share_id: str, url: str) -> dict:
    return {'id': share_id, 'url': url}


def _share_access_payload(share: ShareLink) -> dict:
    return {'access_granted': True, 'share_id': share.id} if share.password_hash else {}


@router.get('/api/projects/{project_id}/shares')
def list_project_shares(
    project_id: str,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    vueio_session: str | None = Cookie(None),
):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    require_horizon_project_access(db, project_id, user, auth_mode='session', required_role='owner')

    page_limit = max(1, min(limit, 200))
    page_offset = max(0, offset)
    query = db.query(ShareLink).filter(ShareLink.project_id == project_id)
    if active_only:
        now = time.time()
        query = query.filter(ShareLink.is_active.is_(True)).filter(or_(ShareLink.expires_at.is_(None), ShareLink.expires_at >= now))

    total = query.count()
    shares = query.order_by(ShareLink.created_at.desc()).offset(page_offset).limit(page_limit).all()
    project_cache = {}
    return {
        'shares': [serialize_share_for_management(share, db, project_cache) for share in shares],
        'total': total,
        'limit': page_limit,
        'offset': page_offset,
        'active_only': active_only,
    }


@router.put('/api/projects/{project_id}/shares/{share_id}')
def update_project_share(
    project_id: str,
    share_id: str,
    data: ProjectShareUpdateRequest,
    db: Session = Depends(get_db),
    vueio_session: str | None = Cookie(None),
):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    require_horizon_project_access(db, project_id, user, auth_mode='session', required_role='owner')

    share = db.query(ShareLink).filter(ShareLink.id == share_id, ShareLink.project_id == project_id).first()
    if not share:
        raise HTTPException(status_code=404, detail='Share not found')

    apply_share_management_update(
        share,
        expires_at=data.expires_at,
        password=data.password,
        is_active=data.is_active,
        allow_download=data.allow_download,
        allow_upload=data.allow_upload,
    )
    db.commit()
    db.refresh(share)
    return {'status': 'updated', 'share': serialize_share_for_management(share, db, {})}



def _get_shared_horizon_project(share: ShareLink, db: Session):
    if not share.project_id:
        raise HTTPException(status_code=404, detail='Project not found')
    return get_horizon_project(db, share.project_id)


def _get_shared_horizon_page(share: ShareLink, db: Session):
    if share.share_type != 'page' or not share.project_id or not share.page_id:
        raise HTTPException(status_code=404, detail='Page not found')
    return get_horizon_page_by_ref(db, share.project_id, share.page_id)


def _resolve_shared_horizon_tracker(share: ShareLink, tracker_name: str, db: Session):
    project = _get_shared_horizon_project(share, db)
    if share.share_type == 'page':
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
        page = _get_shared_horizon_page(share, db)
        if not page_allows_tracker(db, page, tracker):
            raise HTTPException(status_code=403, detail='This page does not grant access to the requested tracker')
    else:
        shared_tracker = get_horizon_tracker_for_share(db, share)
        try:
            tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            # Old direct share URLs may still contain the display name from
            # before a rename. The share itself remains scoped to one tracker.
            tracker = shared_tracker
        if tracker.id != shared_tracker.id:
            raise HTTPException(status_code=403, detail='This share does not grant access to the requested tracker')
    return project, tracker


def apply_share_tracker_filters(shots: list[dict], share: ShareLink, *, strip_internal_fields: bool = False) -> list[dict]:
    filtered = []
    for raw_shot in shots or []:
        shot = dict(raw_shot or {})
        versions = [dict(version or {}) for version in published_versions(shot.get('versions') or [])]
        if not versions:
            continue
        if strip_internal_fields:
            shot.pop('_originalId', None)
            for version in versions:
                version.pop('share_state', None)
                version.pop('published_at', None)
        latest = versions[-1]
        shot['versions'] = versions
        shot['latest_version_label'] = latest.get('label') or latest.get('version')
        shot['latest_media_asset_id'] = latest.get('media_asset_id')
        filtered.append(shot)
    return filtered


def _allowlisted_dict(payload: dict | None, fields: tuple[str, ...]) -> dict:
    source = payload if isinstance(payload, dict) else {}
    return {
        field: source[field]
        for field in fields
        if field in source
    }


def _public_assignee_payload(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return _allowlisted_dict(payload, ('id', 'display_name'))


def _public_version_payload(payload: dict) -> dict:
    result = _allowlisted_dict(payload, (
        'id',
        'version',
        'label',
        'media_asset_id',
        'version_id',
        'horizons_media_asset_id',
        'horizons_shot_version_id',
        'media_entity_type',
        'media_entity_id',
        'media_entity_key',
        'notes',
        'created_at',
        'updated_at',
        'exists',
        'needs_transcode',
        'is_video',
        'is_image',
        'is_pdf',
    ))
    # Shared media is resolved by stable object IDs. Keep only the display name
    # expected by the current tracker UI, never an internal directory path.
    display_name = Path(str(payload.get('file_path') or payload.get('path') or '')).name
    result['path'] = display_name
    result['file_path'] = display_name
    return result


def _public_shot_payload(payload: dict) -> dict:
    result = _allowlisted_dict(payload, (
        'id',
        'shot_id',
        'description',
        'status',
        'category',
        'tag',
        'latest_version_label',
        'latest_media_asset_id',
        'created_at',
        'updated_at',
    ))
    assignees = [
        item
        for item in (
            _public_assignee_payload(assignee)
            for assignee in (payload.get('assignees') or [])
        )
        if item
    ]
    assignee = _public_assignee_payload(payload.get('assignee'))
    result['assignees'] = assignees
    result['assignee'] = assignee
    result['assignee_user_ids'] = [
        item['id']
        for item in assignees
        if item.get('id')
    ]
    result['assignee_user_id'] = (
        assignee.get('id')
        if assignee
        else (result['assignee_user_ids'][0] if result['assignee_user_ids'] else None)
    )
    result['versions'] = [
        _public_version_payload(version)
        for version in (payload.get('versions') or [])
    ]
    return result


def _public_tracker_payload(payload: dict) -> dict:
    result = _allowlisted_dict(payload, (
        'id',
        'slug',
        'name',
        'categories',
        'tags',
        'nodeViewLayout',
        'created_at',
        'updated_at',
        'shot_count',
        'active_shot_count',
    ))
    settings = _allowlisted_dict(
        payload.get('settings'),
        ('comparison', 'details', 'brief_preview', 'delivery'),
    )
    result['settings'] = settings
    result['shots'] = [
        _public_shot_payload(shot)
        for shot in (payload.get('shots') or [])
    ]
    result['shot_count'] = len(result['shots'])
    result['active_shot_count'] = len(result['shots'])
    return result


def _public_page_resource(payload: dict) -> dict:
    if payload.get('kind') == 'url':
        return _allowlisted_dict(payload, ('id', 'kind', 'label', 'url'))
    return _allowlisted_dict(payload, (
        'id',
        'kind',
        'label',
        'path',
        'name',
        'type',
        'size',
        'size_formatted',
        'extension',
        'is_video',
        'is_image',
        'is_pdf',
        'duration',
        'duration_formatted',
        'needs_transcode',
        'exists',
        'media_asset_id',
        'horizons_media_asset_id',
    ))


def _public_page_payload(payload: dict) -> dict:
    result = _allowlisted_dict(payload, (
        'id',
        'slug',
        'title',
        'description',
        'created_at',
        'updated_at',
        'type',
    ))
    blocks = []
    for block in payload.get('blocks') or []:
        block_type = block.get('type')
        public_block = _allowlisted_dict(block, ('id', 'type', 'title'))
        if block_type == 'text':
            public_block['body'] = block.get('body') or ''
        elif block_type == 'tracker_list':
            public_block['trackers'] = [
                _allowlisted_dict(tracker, (
                    'id',
                    'slug',
                    'name',
                    'path',
                    'type',
                    'created_at',
                    'updated_at',
                    'shot_count',
                    'total_duration',
                    'total_frames',
                    'total_versions',
                    'done_shots',
                    'average_shot_duration',
                    'status_breakdown',
                ))
                for tracker in (block.get('trackers') or [])
                if int(tracker.get('shot_count') or 0) > 0
            ]
        elif block_type == 'resource_list':
            public_block['resources'] = [
                _public_page_resource(resource)
                for resource in (block.get('resources') or [])
            ]
        elif block_type == 'upload_inbox':
            public_block.update(_allowlisted_dict(
                block,
                ('description', 'enabled', 'target_path'),
            ))
        blocks.append(public_block)
    result['blocks'] = blocks
    return result


def _public_project_payload(payload: dict) -> dict:
    result = _allowlisted_dict(payload, (
        'id',
        'slug',
        'title',
        'description',
        'status',
        'created_at',
        'updated_at',
        'due_date',
        'tracker_count',
        'shot_count',
        'version_count',
        'source',
    ))
    result['thumbnail_path'] = (
        '__entity_thumbnail__'
        if payload.get('thumbnail_path')
        else None
    )
    return result


def _public_share_info_payload(payload: dict) -> dict:
    result = _allowlisted_dict(payload, (
        'share_type',
        'path',
        'is_folder',
        'project_id',
        'page_id',
        'project_title',
        'allow_download',
        'allow_upload',
        'request_files',
        'tracker_id',
        'tracker_name',
        'project_source',
        'media_asset_id',
        'horizons_shot_version_id',
    ))
    result['thumbnail_path'] = (
        '__entity_thumbnail__'
        if payload.get('project_id') and payload.get('thumbnail_path')
        else None
    )
    return result


def apply_share_tracker_payload(payload: dict, share: ShareLink) -> dict:
    payload['shots'] = apply_share_tracker_filters(
        payload.get('shots', []),
        share,
        strip_internal_fields=True,
    )
    tags = []
    for shot in payload['shots']:
        tag = str(shot.get('category') or shot.get('tag') or '').strip()
        if tag and tag not in tags:
            tags.append(tag)
    payload['categories'] = tags
    payload['tags'] = tags
    payload['shot_count'] = len(payload['shots'])
    payload['active_shot_count'] = len(payload['shots'])
    settings = dict(payload.get('settings') or {})
    settings.pop('version_review', None)
    payload['settings'] = settings
    return _public_tracker_payload(payload)


@router.post('/api/share')
def create_share(data: ShareCreateRequest, db: Session = Depends(get_db), vueio_session: str | None = Cookie(None)):
    user = require_admin(vueio_session)
    if not data.path and data.path != '':
        raise HTTPException(status_code=400, detail='Path is required')

    normalized_path = _normalize_share_path(data.path)
    try:
        file_path = get_safe_path(normalized_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail='Invalid path') from exc
    if data.request_files and not file_path.is_dir():
        raise HTTPException(status_code=400, detail='File requests require a folder')

    password_hash = hash_share_password(data.password)
    media_asset = None if file_path.is_dir() else register_media_asset(db, None, normalized_path, storage_scope='media_root')
    if not file_path.is_dir() and media_asset is None:
        raise HTTPException(status_code=409, detail='The file changed while the share was being created; try again')

    share = create_share_link_with_retry(
        db,
        lambda share_id: ShareLink(
            id=share_id,
            path=normalized_path,
            is_folder=file_path.is_dir(),
            share_type='folder' if file_path.is_dir() else 'file',
            media_asset_id=media_asset.id if media_asset else None,
            created_by=user['username'] if user else None,
            expires_at=data.expires_at if data.expires_at and data.expires_at > 0 else None,
            password_hash=password_hash,
            allow_download=bool(data.allow_download and not data.request_files),
            allow_upload=bool((data.allow_upload or data.request_files) and file_path.is_dir()),
            request_files=bool(data.request_files),
        ),
    )
    db.commit()
    db.refresh(share)

    return _serialize_share_created(share.id, f'/s/{share.id}')


@router.get('/api/share/{share_id}')
def get_share(share_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(
        share_id,
        None,
        db,
        ['file', 'folder', 'project-file', 'project-folder', 'project', 'tracker', 'page'],
        share_token=share_token,
        track_access=True,
        allow_file_request=True,
    )
    return {
        'id': share.id,
        'path': share.path,
        'is_folder': share.is_folder,
        'media_asset_id': share.media_asset_id,
        'share_type': share.share_type,
        'project_id': share.project_id,
        'tracker_id': share.tracker_id,
        'tracker_name': share.tracker_name,
        'page_id': share.page_id,
        'allow_download': share.allow_download,
        'allow_upload': share.allow_upload,
        'request_files': share.request_files,
    } | _share_access_payload(share)


@router.post('/api/share/{share_id}/unlock')
async def unlock_share(
    share_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        request,
        settings.PUBLIC_SHARE_PASSWORD_RATE_LIMIT,
        scope='public-share-password',
    )
    data = await _read_share_unlock_request(request)
    share = validate_share(
        share_id,
        data.password,
        db,
        ['file', 'folder', 'project-file', 'project-folder', 'project', 'tracker', 'page'],
        track_access=False,
        allow_file_request=True,
        allow_password_auth=True,
    )
    response.set_cookie(
        key='vueio_share_access',
        value=issue_share_access_token(share),
        max_age=60 * 60,
        path='/api',
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite='strict',
    )
    response.headers['Cache-Control'] = 'no-store'
    return _share_access_payload(share)


@router.post('/api/projects/{project_id}/share')
def share_project(project_id: str, data: ProjectShareCreateRequest | None = None, db: Session = Depends(get_db), vueio_session: str | None = Cookie(None)):
    session_user = get_user_from_session(vueio_session)
    if not session_user:
        raise HTTPException(status_code=401, detail='Authentication required')
    project = get_horizon_project(db, project_id)
    if project is not None:
        _project, _access_role = require_horizon_project_access(db, project_id, session_user, auth_mode='session', required_role='owner')
        user = session_user
    else:
        user = require_admin(vueio_session)
    if data is None:
        data = ProjectShareCreateRequest()

    share_type = 'project'
    tracker_name = None
    tracker_id = None
    page_id = None
    tracker_ref = data.tracker_id or data.tracker_name
    if tracker_ref and data.page_id:
        raise HTTPException(status_code=400, detail='Share either a tracker or a page, not both')
    if data.page_id:
        page = get_horizon_page_by_ref(db, project_id, data.page_id)
        share_type = 'page'
        page_id = page.id
    elif tracker_ref:
        tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
        share_type = 'tracker'
        tracker_id = tracker.id
        tracker_name = tracker.name

    password_hash = hash_share_password(data.password)

    share = create_share_link_with_retry(
        db,
        lambda share_id: ShareLink(
            id=share_id,
            path=None,
            is_folder=False,
            share_type=share_type,
            project_id=project_id,
            tracker_id=tracker_id,
            tracker_name=tracker_name,
            page_id=page_id,
            created_by=user['username'],
            expires_at=data.expires_at if data.expires_at and data.expires_at > 0 else None,
            password_hash=password_hash,
            allow_download=data.allow_download,
            allow_upload=bool(page_id and get_page_upload_targets(page)) if data.page_id else False,
        ),
    )
    db.commit()
    db.refresh(share)

    return _serialize_share_created(share.id, f'/p/{share.id}')


@router.get('/api/projects/shared/{share_id}')
def get_shared_project(share_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=True)
    project = _get_shared_horizon_project(share, db)

    payload = serialize_horizon_project(db, project)
    payload.setdefault('due_date', None)
    payload.setdefault('thumbnail_path', None)
    thumbnail_path = str(payload.get('thumbnail_path') or '').strip()
    if thumbnail_path and not thumbnail_path.startswith('__'):
        held_asset_ids = held_media_asset_ids_for_project(db, project.id)
        held_paths = held_media_paths_for_project(db, project.id)
        thumbnail_asset = get_horizon_media_asset_by_path(db, project.id, thumbnail_path)
        thumbnail_full_path, _cache_key, _scope = resolve_project_link_target(
            project.id,
            thumbnail_path,
        )
        if (
            (thumbnail_asset is not None and str(thumbnail_asset.id) in held_asset_ids)
            or (
                thumbnail_full_path is not None
                and thumbnail_full_path.resolve(strict=False) in held_paths
            )
        ):
            payload['thumbnail_path'] = None
    payload = _public_project_payload(payload)
    payload['_share_allow_download'] = share.allow_download
    payload['_share_allow_upload'] = share.allow_upload
    payload['_share_type'] = share.share_type
    payload['_share_tracker_id'] = share.tracker_id
    payload['_share_tracker_name'] = share.tracker_name

    if share.share_type == 'page' and share.page_id:
        page = _get_shared_horizon_page(share, db)
        page_payload = _public_page_payload(serialize_horizon_page(db, page, public=True))
        public_tracker_ids = {
            str(tracker.get('id'))
            for block in page_payload.get('blocks') or []
            for tracker in (block.get('trackers') or [])
            if tracker.get('id')
        }
        public_summary = published_scope_summary(
            db,
            project.id,
            tracker_ids=public_tracker_ids,
        )
        payload.update(public_summary)
        payload['tracker_count'] = len(public_tracker_ids)
        payload['updated_at'] = public_summary['updated_at'] or payload.get('created_at')
        payload['page'] = page_payload
        payload['_current_page'] = page.slug
        payload['_open_page'] = True
        payload['_trackers'] = []
        payload['shots'] = []
        payload['_open_tracker'] = False
    elif share.share_type == 'tracker' and (share.tracker_id or share.tracker_name):
        tracker = get_horizon_tracker_for_share(db, share)
        tracker_payload = apply_share_tracker_payload(serialize_horizon_tracker_detail(db, tracker), share)
        payload['shots'] = tracker_payload.get('shots', [])
        payload['categories'] = tracker_payload.get('categories', [])
        payload['tags'] = tracker_payload.get('tags', [])
        payload['nodeViewLayout'] = tracker_payload.get('nodeViewLayout', {})
        payload['settings'] = tracker_payload.get('settings', {})
        payload['tracker_count'] = 1
        payload['shot_count'] = tracker_payload.get('shot_count', 0)
        payload['version_count'] = sum(
            len(shot.get('versions') or [])
            for shot in tracker_payload.get('shots', [])
        )
        payload['updated_at'] = (
            latest_published_at_for_tracker(db, project.id, tracker.id)
            or payload.get('created_at')
        )
        payload['_share_tracker_id'] = tracker.id
        payload['_share_tracker_name'] = tracker.name
        payload['_current_tracker_id'] = tracker.id
        payload['_current_tracker_slug'] = tracker.slug
        payload['_current_tracker'] = tracker.name
        payload['_open_tracker'] = True
    else:
        public_summary = published_scope_summary(db, project.id)
        payload.update(public_summary)
        payload['updated_at'] = public_summary['updated_at'] or payload.get('created_at')
        public_trackers = [
            tracker
            for tracker in list_horizon_trackers(db, project.id)
            if published_shot_ids_for_tracker(db, project.id, tracker.id)
        ]
        payload['_trackers'] = [tracker.name for tracker in public_trackers]
        payload['tracker_count'] = len(public_trackers)
        payload['shots'] = []
        payload['_open_tracker'] = False

    payload.update(_share_access_payload(share))
    return payload


@router.post('/api/projects/{project_id}/share-content')
def share_project_content(project_id: str, data: ProjectContentShareRequest, db: Session = Depends(get_db), vueio_session: str | None = Cookie(None)):
    session_user = get_user_from_session(vueio_session)
    if not session_user:
        raise HTTPException(status_code=401, detail='Authentication required')
    project = get_horizon_project(db, project_id)
    if project is not None:
        _project, _access_role = require_horizon_project_access(db, project_id, session_user, auth_mode='session', required_role='owner')
        user = session_user
    else:
        user = require_admin(vueio_session)
    project_dir = resolve_project_root(project) if project is not None else get_project_dir(project_id)
    normalized_path = _normalize_share_path(data.path)
    target_path = project_dir / normalized_path
    if data.request_files and not data.is_folder:
        raise HTTPException(status_code=400, detail='File requests require a folder')

    links = load_project_links(project_id)
    is_linked = find_link_target(links.get('links', []), normalized_path) is not None
    if data.is_folder:
        is_horizons_asset = _horizons_virtual_folder_exists(project_id, normalized_path, db)
    else:
        is_horizons_asset = get_horizon_media_asset_by_path(db, project_id, normalized_path) is not None

    if not is_linked and not target_path.exists() and not is_horizons_asset:
        raise HTTPException(status_code=404, detail='File or folder not found')
    if data.request_files:
        verify_path_in_project(target_path, project_dir)
        if not target_path.is_dir():
            raise HTTPException(status_code=400, detail='File request destination must be a physical project folder')
        if not os.access(target_path, os.W_OK):
            raise HTTPException(status_code=403, detail='File request destination is not writable by the server')

    password_hash = hash_share_password(data.password)

    share_type = 'project-folder' if data.is_folder else 'project-file'
    media_asset = None
    if not data.is_folder:
        link_match = find_link_target(links.get('links', []), normalized_path)
        if link_match:
            link, suffix = link_match
            source_path = str(link.get('source_path') or '').strip()
            resolved_source_path = join_rel_path(source_path, suffix) if suffix else source_path
            media_asset = register_media_asset(
                db,
                project_id,
                resolved_source_path,
                storage_scope=link_storage_scope(link),
            )
        else:
            media_asset = get_media_asset_by_path(db, project_id, normalized_path) or register_media_asset(db, project_id, normalized_path, storage_scope='project')
        if media_asset is None:
            raise HTTPException(status_code=409, detail='The file changed while the share was being created; try again')

    share = create_share_link_with_retry(
        db,
        lambda share_id: ShareLink(
            id=share_id,
            path=normalized_path,
            is_folder=data.is_folder,
            share_type=share_type,
            project_id=project_id,
            media_asset_id=media_asset.id if media_asset else None,
            created_by=user['username'],
            expires_at=data.expires_at if data.expires_at and data.expires_at > 0 else None,
            password_hash=password_hash,
            allow_download=bool(data.allow_download and not data.request_files),
            allow_upload=bool((data.allow_upload or data.request_files) and data.is_folder),
            request_files=bool(data.request_files),
        ),
    )
    db.commit()
    db.refresh(share)

    # Keep public share URLs opaque. The share record carries the authorized path;
    # the frontend loads it from /info instead of exposing folder/project names in the URL.
    return _serialize_share_created(share.id, f'/p/{share.id}/f')


@router.get('/api/projects/shared/{share_id}/info')
def get_shared_content_info(share_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(
        share_id,
        None,
        db,
        ['file', 'folder', 'project-file', 'project-folder', 'project', 'tracker', 'page'],
        share_token=share_token,
        track_access=False,
        allow_file_request=True,
    )
    return _public_share_info_payload(
        get_shared_content_info_dict(share, db=db),
    ) | _share_access_payload(share)


@router.get('/api/projects/shared/{share_id}/tracker/{tracker_name}')
def get_shared_tracker(share_id: str, tracker_name: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if share.share_type in {'tracker', 'page'}:
        _project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    return apply_share_tracker_payload(serialize_horizon_tracker_detail(db, tracker), share)


@router.post('/api/projects/shared/{share_id}/tracker/{tracker_name}/views')
def record_shared_tracker_view(
    share_id: str,
    tracker_name: str,
    data: TrackerViewRequest,
    request: Request,
    share_token: str | None = None,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, settings.PUBLIC_TRACKER_VIEW_RATE_LIMIT, scope='public-tracker-view')
    share = validate_share(
        share_id,
        None,
        db,
        ['project', 'tracker', 'page'],
        share_token=share_token,
        track_access=False,
    )
    if share.share_type in {'tracker', 'page'}:
        project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    allowed_shot_ids = None
    allowed_version_ids = None
    if data.action == 'media':
        allowed_shot_ids = published_shot_ids_for_tracker(db, project.id, tracker.id)
        allowed_version_ids = published_version_ids_for_tracker(db, project.id, tracker.id)
    return record_tracker_view(
        db,
        request=request,
        project_id=project.id,
        tracker_id=tracker.id,
        data=data,
        source='share',
        share=share,
        allowed_shot_ids=allowed_shot_ids,
        allowed_version_ids=allowed_version_ids,
    )


@router.get('/api/projects/shared/{share_id}/tracker/{tracker_name}/delivery-logo')
def get_shared_tracker_delivery_logo(share_id: str, tracker_name: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if share.share_type in {'tracker', 'page'}:
        _project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    return build_delivery_logo_response(tracker_settings_for(tracker)['delivery']['logo_upload_name'])


@router.post('/api/projects/shared/{share_id}/tracker/{tracker_name}/download-latest-zip')
def download_shared_tracker_latest_versions_zip(share_id: str, tracker_name: str, data: SharedTrackerLatestDownloadRequest, background_tasks: BackgroundTasks, request: Request, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    if share.share_type in {'tracker', 'page'}:
        project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    create_download_event(
        db,
        request=request,
        source='share',
        share_id=share.id,
        project_id=project.id,
        tracker_id=tracker.id,
        event_type='download_all',
        resource_type='tracker_latest_zip',
        resource_id=tracker.id,
        resource_name=tracker.name,
        filename=data.filename,
        paths=data.shot_ids or [],
        metadata={'share_type': share.share_type, 'selected_shots': bool(data.shot_ids)},
        create_tracker_activity=True,
    )
    return build_tracker_latest_versions_zip(
        db,
        project=project,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        background_tasks=background_tasks,
        shot_refs=data.shot_ids,
        filename=data.filename,
        share=share,
    )


@router.post('/api/projects/shared/{share_id}/tracker/{tracker_name}/download-latest-zip-job')
def create_shared_tracker_latest_versions_zip_job(share_id: str, tracker_name: str, data: SharedTrackerLatestDownloadRequest, request: Request, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    if share.share_type in {'tracker', 'page'}:
        project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    create_download_event(
        db,
        request=request,
        source='share',
        share_id=share.id,
        project_id=project.id,
        tracker_id=tracker.id,
        event_type='download_all',
        resource_type='tracker_latest_zip_job',
        resource_id=tracker.id,
        resource_name=tracker.name,
        filename=data.filename,
        paths=data.shot_ids or [],
        metadata={'share_type': share.share_type, 'selected_shots': bool(data.shot_ids)},
        create_tracker_activity=True,
    )
    return start_tracker_latest_versions_zip_job(
        db,
        project=project,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        shot_refs=data.shot_ids,
        filename=data.filename,
        share=share,
    )


@router.post('/api/projects/shared/{share_id}/tracker/{tracker_name}/download-latest-zip-form')
def download_shared_tracker_latest_versions_zip_form(
    share_id: str,
    tracker_name: str,
    background_tasks: BackgroundTasks,
    shot_ids: str | None = Form(None),
    filename: str | None = Form(None),
    share_token: str | None = None,
    db: Session = Depends(get_db),
):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    if share.share_type in {'tracker', 'page'}:
        project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    return build_tracker_latest_versions_zip(
        db,
        project=project,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        background_tasks=background_tasks,
        shot_refs=_parse_shared_tracker_download_form_shot_ids(shot_ids),
        filename=filename,
        share=share,
    )


@router.get('/api/projects/shared/{share_id}/tracker/{tracker_name}/stats')
def get_shared_tracker_stats(share_id: str, tracker_name: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if share.share_type in {'tracker', 'page'}:
        project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    if not tracker_tool_enabled_for_context(tracker, 'details', share=True):
        raise HTTPException(status_code=403, detail='Details are disabled for this tracker')
    return compute_horizon_tracker_stats(db, tracker, published_only=True)


@router.get('/api/projects/shared/{share_id}/tracker/{tracker_name}/activity')
def get_shared_tracker_activity(
    share_id: str,
    tracker_name: str,
    limit: int = 40,
    before: float | None = None,
    before_id: int | None = None,
    share_token: str | None = None,
    db: Session = Depends(get_db),
):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if share.share_type in {'tracker', 'page'}:
        project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    if not tracker_tool_enabled_for_context(tracker, 'details', share=True):
        raise HTTPException(status_code=403, detail='Details are disabled for this tracker')
    return list_tracker_activity(
        db,
        project_id=tracker.project_id,
        tracker_id=tracker.id,
        limit=limit,
        before=before,
        before_id=before_id,
        visible_shot_ids=published_shot_ids_for_tracker(db, tracker.project_id, tracker.id),
        visible_version_ids=published_version_ids_for_tracker(db, tracker.project_id, tracker.id),
        audience='public',
    )


@router.put('/api/projects/shared/{share_id}/tracker/{tracker_name}/shots/{shot_id}')
def update_shared_shot_status(share_id: str, tracker_name: str, shot_id: str, data: SharedShotStatusUpdate, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project', 'tracker', 'page'], share_token=share_token, track_access=False)
    if share.share_type in {'tracker', 'page'}:
        _project, tracker = _resolve_shared_horizon_tracker(share, tracker_name, db)
    else:
        project = _get_shared_horizon_project(share, db)
        tracker = get_horizon_tracker_by_ref(db, project.id, tracker_name)
    if data.status not in SHOT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(SHOT_STATUSES)}")

    shot = get_horizon_shot_by_ref(db, share.project_id, shot_id, tracker_id=tracker.id)
    if (
        shot.archived_at
        or shot.id not in published_shot_ids_for_tracker(db, share.project_id, tracker.id)
    ):
        raise HTTPException(status_code=404, detail='Horizons shot not found')
    actor = build_tracker_event_actor(source='share', actor_name='Shared reviewer', actor_id=share.id)
    command_ctx = ShotCommandContext(
        project_id=share.project_id,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        access_role='editor',
        actor=ShotCommandActor(user=None, auth_mode='share', source=actor['source'], actor_id=actor['actor_id'], actor_name=actor['actor_name']),
        can_create_shot=False,
        can_update_shot=True,
        can_delete_shot=False,
        can_delete_versions=False,
        can_archive_shot=False,
        restricted_artist=False,
    )
    result = ShotCommandService(db).update_shot(command_ctx, shot, status=data.status, fields_set={'status'})
    for tracker_id in result.stats_dirty_tracker_ids:
        refresh_horizon_tracker_stats_cache(db, get_horizon_tracker_by_ref(db, share.project_id, tracker_id), commit=False)
    db.commit()
    return {'status': 'updated', 'shot_id': shot_id, 'new_status': data.status}


@router.get('/api/projects/shared/{share_id}/contents')
def get_shared_project_folder_contents(share_id: str, path: str = '', include_counts: bool = False, share_token: str | None = None, db: Session = Depends(get_db)):
    share = validate_share(share_id, None, db, ['project-folder', 'project', 'page'], share_token=share_token, track_access=False)
    _get_shared_horizon_project(share, db)
    policy = (
        SharedProjectFolderPolicy(db, share)
        if share.share_type == 'project-folder'
        else SharedPagePolicy(db, share)
        if share.share_type == 'page'
        else SharedProjectPolicy(db, share)
    )
    result = list_content(policy, path, include_counts=include_counts)
    return {'items': result.items, 'path': result.path, 'share_root': result.share_root}


def _require_uploadable_share(share_id: str, db: Session, share_token: str | None = None) -> ShareLink:
    share = validate_share(
        share_id,
        None,
        db,
        ['folder', 'project-folder', 'page'],
        share_token=share_token,
        track_access=False,
        allow_file_request=True,
    )
    if share.project_id:
        from app.services.horizons.projects import require_horizon_project_writable
        require_horizon_project_writable(db, share.project_id)
    if share.share_type == 'folder' and not share.is_folder:
        raise HTTPException(status_code=400, detail='Uploads are only supported for folder shares')
    if share.share_type == 'page':
        _get_shared_horizon_page(share, db)
    if share.share_type not in {'folder', 'project-folder', 'page'}:
        raise HTTPException(status_code=400, detail='Uploads are not supported for this share')
    if not share.allow_upload:
        raise HTTPException(status_code=403, detail='Uploads are disabled for this share')
    return share


def _resolve_shared_upload_base_path(share: ShareLink, target_path: str | None) -> str:
    candidate = _normalize_share_path(target_path or share.path or '')
    root = _normalize_share_path(share.path or '')
    if root and not candidate:
        candidate = root
    if candidate:
        try:
            candidate = require_path_within_shared_root(root, candidate)
        except HTTPException as exc:
            raise HTTPException(status_code=403, detail='Upload target is outside the shared folder') from exc
    target_dir = get_safe_path(candidate)
    if not target_dir.exists():
        raise HTTPException(status_code=404, detail='Upload target folder not found')
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail='Upload target must be a folder')
    if not os.access(target_dir, os.W_OK):
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server')
    return candidate


def _resolve_shared_upload_context(share: ShareLink, target_path: str | None, db: Session) -> tuple[Path, str]:
    if share.share_type == 'folder':
        base_path = _resolve_shared_upload_base_path(share, target_path)
        if share.request_files and base_path != _normalize_share_path(share.path):
            raise HTTPException(status_code=403, detail='File requests upload only to their destination folder')
        return settings.MEDIA_ROOT.resolve(), base_path

    if share.share_type == 'project-folder':
        project_dir = resolve_project_root(_get_shared_horizon_project(share, db)).resolve()
        root = _normalize_share_path(share.path)
        candidate = _normalize_share_path(target_path or root)
        try:
            candidate = require_path_within_shared_root(root, candidate)
        except HTTPException as exc:
            raise HTTPException(status_code=403, detail='Upload target is outside the shared folder') from exc
        if share.request_files and candidate != root:
            raise HTTPException(status_code=403, detail='File requests upload only to their destination folder')
        target_dir = project_dir / candidate
        verify_path_in_project(target_dir, project_dir)
        if not target_dir.exists():
            raise HTTPException(status_code=404, detail='Upload target folder not found')
        if not target_dir.is_dir():
            raise HTTPException(status_code=400, detail='Upload target must be a folder')
        if not os.access(target_dir, os.W_OK):
            raise HTTPException(status_code=403, detail='Upload target is not writable by the server')
        return project_dir, candidate

    page = _get_shared_horizon_page(share, db)
    targets = get_page_upload_targets(page)
    if not targets:
        raise HTTPException(status_code=403, detail='This page does not have an upload inbox')
    candidate = _normalize_share_path(target_path or targets[0])
    if not page_allows_upload_target(page, candidate):
        raise HTTPException(status_code=403, detail='Upload target is not available on this page')
    project_dir = resolve_project_root(get_horizon_project(db, share.project_id)).resolve()
    target_dir = project_dir / candidate
    verify_path_in_project(target_dir, project_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(target_dir)
    if not os.access(target_dir, os.W_OK):
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server')
    return project_dir, candidate


@router.post('/api/share/{share_id}/uploads')
def create_shared_upload_session(
    request: Request,
    share_id: str,
    data: UploadSessionCreateRequest,
    share_token: str | None = None,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, settings.PUBLIC_UPLOAD_CREATE_RATE_LIMIT, scope='public-upload-create')
    share = _require_uploadable_share(share_id, db, share_token=share_token)
    root_dir, base_path = _resolve_shared_upload_context(share, data.target_path, db)
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_SHARED, root_dir=root_dir, base_path=base_path, share_id=share.id)
    session, items = create_authorized_upload_session(
        db,
        upload_scope,
        uploader_name=validate_uploader_name(data.uploader_name),
        client_batch_id=data.client_batch_id,
        manifest=[item.model_dump() for item in data.files],
        client_key=client_rate_limit_key(request),
    )
    return serialize_upload_session(session, items)


@router.get('/api/share/{share_id}/uploads/{session_id}')
def get_shared_upload_session(
    share_id: str,
    session_id: str,
    share_token: str | None = None,
    db: Session = Depends(get_db),
):
    share = _require_uploadable_share(share_id, db, share_token=share_token)
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_SHARED, root_dir=settings.MEDIA_ROOT.resolve(), base_path='', share_id=share.id)
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    return serialize_upload_session(session, items)


@router.patch('/api/share/{share_id}/uploads/{session_id}/items/{item_id}')
async def patch_shared_upload_item(
    share_id: str,
    session_id: str,
    item_id: str,
    request: Request,
    share_token: str | None = None,
    upload_offset: int = Header(..., alias='Upload-Offset'),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, settings.PUBLIC_UPLOAD_CHUNK_RATE_LIMIT, scope='public-upload-chunk')
    share = _require_uploadable_share(share_id, db, share_token=share_token)
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_SHARED, root_dir=settings.MEDIA_ROOT.resolve(), base_path='', share_id=share.id)
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    item = find_upload_item(items, item_id)
    root_dir, _base_path = _resolve_shared_upload_context(share, session.base_path, db)
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_SHARED, root_dir=root_dir, base_path=session.base_path, share_id=share.id)
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


@router.delete('/api/share/{share_id}/uploads/{session_id}/items/{item_id}')
def delete_shared_upload_item(
    share_id: str,
    session_id: str,
    item_id: str,
    share_token: str | None = None,
    db: Session = Depends(get_db),
):
    share = _require_uploadable_share(share_id, db, share_token=share_token)
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_SHARED, root_dir=settings.MEDIA_ROOT.resolve(), base_path='', share_id=share.id)
    session, items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    item = find_upload_item(items, item_id)
    session, items = cancel_authorized_upload_item(db, upload_scope, session=session, item=item)
    return serialize_upload_session(session, items)


@router.delete('/api/share/{share_id}/uploads/{session_id}')
def delete_shared_upload_session(
    share_id: str,
    session_id: str,
    share_token: str | None = None,
    db: Session = Depends(get_db),
):
    share = _require_uploadable_share(share_id, db, share_token=share_token)
    upload_scope = AuthorizedUploadScope(scope_type=UPLOAD_SCOPE_SHARED, root_dir=settings.MEDIA_ROOT.resolve(), base_path='', share_id=share.id)
    session, _items = get_authorized_upload_session(db, upload_scope, session_id=session_id)
    session, items = cancel_authorized_upload_session(db, upload_scope, session=session)
    return serialize_upload_session(session, items)
