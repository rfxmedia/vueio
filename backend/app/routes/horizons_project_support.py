from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.auth import get_request_user
from app.services.file_access import require_user_file_browser_read_access
from app.services.horizons_fresh import (
    get_horizon_project,
    get_visible_horizon_media_asset_by_path,
    is_horizon_workspace_root_path,
    is_restricted_horizon_artist,
    require_horizon_user_workspace_path,
    require_horizon_project_access,
    select_horizon_preview_asset,
    update_horizon_project,
)
from app.services.horizons.media import get_visible_horizon_media_assets_by_paths
from app.services.hls_streaming import get_hls_thumbnail_source
from app.services.horizon_pages import get_horizon_page_by_ref, page_allows_path
from app.services.media import (
    DELIVERY_POSTER_WIDTH,
    IMAGE_EXTENSIONS,
    THUMBNAIL_WIDTH,
    VIDEO_EXTENSIONS,
    build_thumbnail_response,
    format_duration_label,
    format_size,
    get_video_duration_quick,
    probe_cached_video_durations,
    queue_thumbnail_generation,
)
from app.services.media_serving import MAX_CUSTOM_THUMBNAIL_BYTES, DownloadAuditSpec, serve_zip_entries
from app.services.upload_payloads import read_bounded_upload, require_valid_image
from app.services.horizon_entity_thumbnails import (
    build_horizon_entity_upload_name,
    get_horizon_entity_thumbnail_record,
    get_horizon_entity_upload_path,
    normalize_horizon_thumbnail_entity,
    set_horizon_entity_thumbnail_record,
)
from app.services.media_assets import attach_canonical_media_identity
from app.services.media_resolution import (
    delivery_poster_cache_path_for_identity,
    delivery_poster_cache_path_for_media,
    generated_thumbnail_cache_path_for_identity,
    resolve_media_asset_path,
    resolve_media_full_path,
    thumbnail_cache_path_for_media,
)
from app.services.project_content_gateway import HorizonsProjectAuthPolicy, collect_zip
from app.services.share_access import _path_within_shared_root, is_horizons_share_project, validate_share
from app.services.shot_registry import list_horizon_shot_registry_entries

settings = get_settings()
router = APIRouter(tags=['horizons-project-support'])


def _is_delivery_thumbnail_variant(variant: str | None) -> bool:
    return str(variant or '').strip().lower() in {'delivery', 'delivery_poster', 'poster'}


def _ensure_mutable_thumbnail_entity(entity_type: str, entity_path: str | None) -> None:
    if entity_type == 'folder' and is_horizon_workspace_root_path(entity_path):
        raise HTTPException(status_code=400, detail='Workspace folders cannot be customized')


def _authorize_thumbnail_mutation(
    db: Session,
    project_id: str,
    user: dict,
    access_role: str,
    entity_type: str,
    entity_path: str | None,
) -> str | None:
    _ensure_mutable_thumbnail_entity(entity_type, entity_path)
    if not is_restricted_horizon_artist(user, access_role):
        return entity_path
    if entity_type != 'folder':
        raise HTTPException(status_code=403, detail='Artists cannot update the project thumbnail')
    return require_horizon_user_workspace_path(
        db,
        project_id,
        user,
        entity_path,
        allow_workspace_root=False,
    )


class HorizonsBatchMediaInfoRequest(BaseModel):
    paths: list[str]


class HorizonsFolderZipRequest(BaseModel):
    path: str
    filename: Optional[str] = None


class HorizonsEntityThumbnailSelectRequest(BaseModel):
    entity_type: str = 'project'
    path: Optional[str] = None
    source_path: str


def _require_horizons_viewer(project_id: str, vueio_session: str | None, x_vueio_agent_key: str | None, db: Session):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    return user, access_role, project


def _require_horizons_editor(project_id: str, vueio_session: str | None, db: Session):
    user, auth_mode = get_request_user(vueio_session, None)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    return user, access_role, project


def _resolve_horizons_thumbnail_viewer(project_id: str, vueio_session: str | None, x_vueio_agent_key: str | None, share_id: str | None, share_token: str | None, entity_type: str, entity_path: str | None, db: Session):
    try:
        normalized_type, normalized_path = normalize_horizon_thumbnail_entity(entity_type, entity_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid thumbnail target') from exc
    if share_id:
        share = validate_share(share_id, None, db, ['project', 'project-folder', 'tracker', 'project-file', 'page'], share_token=share_token, track_access=False)
        if not is_horizons_share_project(share) or share.project_id != project_id:
            raise HTTPException(status_code=403, detail='Access denied')
        if normalized_type == 'folder':
            if share.share_type in {'tracker', 'project-file'}:
                raise HTTPException(status_code=403, detail='Access denied - folder thumbnail unavailable for this share')
            if share.share_type == 'project-folder' and share.path and not _path_within_shared_root(share.path, normalized_path or ''):
                raise HTTPException(status_code=403, detail='Access denied - path outside shared folder')
            if share.share_type == 'page':
                page = get_horizon_page_by_ref(db, project_id, share.page_id or '')
                if not page_allows_path(page, normalized_path or ''):
                    raise HTTPException(status_code=403, detail='Access denied - folder is not referenced by this page')
        return None, 'share', get_horizon_project(db, project_id)
    return _require_horizons_viewer(project_id, vueio_session, x_vueio_agent_key, db)


def _resolve_horizons_thumbnail_source(
    db: Session,
    project_id: str,
    source_path: str,
    *,
    storage_scope: str | None = 'media_root',
    user: dict | None = None,
    access_role: str | None = None,
    delivery_poster: bool = False,
):
    normalized_source = str(source_path or '').strip().strip('/')
    if not normalized_source:
        raise HTTPException(status_code=400, detail='Source path is required')

    asset = None
    if storage_scope == 'project':
        asset = get_visible_horizon_media_asset_by_path(db, project_id, normalized_source, user=user, access_role=access_role)
    if asset is not None:
        full_path, cache_key, resolved_scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
    else:
        full_path, cache_key = resolve_media_full_path(normalized_source, project_id, storage_scope=storage_scope)
        resolved_scope = storage_scope

    if not full_path or not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail='Thumbnail source not found')
    if access_role == 'share':
        from app.services.horizons.version_publication import held_media_paths_for_project

        if full_path.resolve(strict=False) in held_media_paths_for_project(db, project_id):
            raise HTTPException(status_code=404, detail='Thumbnail source not found')
    if full_path.suffix.lower() not in IMAGE_EXTENSIONS and full_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail='Thumbnail source must be an image or video')

    if delivery_poster:
        thumb_path = delivery_poster_cache_path_for_identity(cache_key) if cache_key else delivery_poster_cache_path_for_media(project_id, normalized_source, full_path, storage_scope=resolved_scope)
    else:
        thumb_path = generated_thumbnail_cache_path_for_identity(cache_key) if cache_key else thumbnail_cache_path_for_media(project_id, normalized_source, full_path, storage_scope=resolved_scope)
    return normalized_source, full_path, thumb_path, resolved_scope, cache_key


def _set_project_thumbnail_marker(db: Session, project_id: str):
    update_horizon_project(db, project_id, thumbnail_path='__entity_thumbnail__', fields_set={'thumbnail_path'})


def _build_project_thumbnail_response(full_path: Path, thumb_path: Path, *, missing_detail: str, cache_key: str | None, queue_missing: bool, delivery_poster: bool):
    preferred_source = None if delivery_poster else (get_hls_thumbnail_source(cache_key) if cache_key else None)
    return build_thumbnail_response(
        full_path,
        thumb_path,
        missing_detail=missing_detail,
        preferred_video_source=preferred_source,
        queue_missing=queue_missing,
        thumbnail_width=DELIVERY_POSTER_WIDTH if delivery_poster else THUMBNAIL_WIDTH,
    )


def _resolve_legacy_project_thumbnail(db: Session, project_id: str, project, user: dict | None, access_role: str | None, *, queue_missing: bool = True, delivery_poster: bool = False):
    thumbnail_path = str(project.thumbnail_path or '').strip()
    if thumbnail_path and thumbnail_path.startswith('__uploaded_project_'):
        upload_path = settings.thumbnail_dir / f'project_{project_id}.jpg'
        if upload_path.exists():
            return FileResponse(upload_path, media_type='image/jpeg')
        raise HTTPException(status_code=404, detail='No project thumbnail')

    if thumbnail_path and not thumbnail_path.startswith('__entity_thumbnail__'):
        _source_path, full_path, thumb_path, _resolved_scope, cache_key = _resolve_horizons_thumbnail_source(
            db,
            project_id,
            thumbnail_path,
            storage_scope=None,
            user=user,
            access_role=access_role,
            delivery_poster=delivery_poster,
        )
        return _build_project_thumbnail_response(full_path, thumb_path, missing_detail='No project thumbnail', cache_key=cache_key, queue_missing=queue_missing, delivery_poster=delivery_poster)

    asset = select_horizon_preview_asset(db, project_id, user=user, access_role=access_role)
    if not asset:
        raise HTTPException(status_code=404, detail='No project thumbnail')
    full_path, cache_key, _storage_scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail='No project thumbnail')
    cache_identity = cache_key or f'asset:{asset.id}'
    thumb_path = delivery_poster_cache_path_for_identity(cache_identity) if delivery_poster else generated_thumbnail_cache_path_for_identity(cache_identity)
    return _build_project_thumbnail_response(full_path, thumb_path, missing_detail='No project thumbnail', cache_key=cache_identity, queue_missing=queue_missing, delivery_poster=delivery_poster)


def resolve_horizon_entity_thumbnail_response(db: Session, project_id: str, entity_type: str, entity_path: str | None, *, user: dict | None = None, access_role: str | None = None, project=None, queue_missing: bool = True, delivery_poster: bool = False):
    try:
        normalized_type, normalized_path = normalize_horizon_thumbnail_entity(entity_type, entity_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid thumbnail target') from exc
    record = get_horizon_entity_thumbnail_record(project_id, normalized_type, normalized_path)
    if record:
        mode = str(record.get('mode') or '').strip().lower()
        if mode == 'uploaded':
            upload_name = str(record.get('upload_name') or '').strip()
            upload_path = get_horizon_entity_upload_path(upload_name)
            if upload_name and upload_path.exists():
                return FileResponse(upload_path)
            raise HTTPException(status_code=404, detail='No thumbnail uploaded')
        if mode == 'source':
            source_path = str(record.get('source_path') or '').strip()
            storage_scope = str(record.get('storage_scope') or 'media_root').strip() or 'media_root'
            _source_path, full_path, thumb_path, _resolved_scope, cache_key = _resolve_horizons_thumbnail_source(
                db,
                project_id,
                source_path,
                storage_scope=storage_scope,
                user=user,
                access_role=access_role,
                delivery_poster=delivery_poster,
            )
            return _build_project_thumbnail_response(full_path, thumb_path, missing_detail='No thumbnail', cache_key=cache_key, queue_missing=queue_missing, delivery_poster=delivery_poster)

    if normalized_type == 'project':
        return _resolve_legacy_project_thumbnail(db, project_id, project or get_horizon_project(db, project_id), user, access_role, queue_missing=queue_missing, delivery_poster=delivery_poster)

    raise HTTPException(status_code=404, detail='No folder thumbnail')


@router.post('/api/horizons/projects/{project_id}/media-info/batch')
def batch_horizons_media_info(project_id: str, payload: HorizonsBatchMediaInfoRequest, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role, _project = _require_horizons_viewer(project_id, vueio_session, x_vueio_agent_key, db)

    paths: list[str] = []
    seen = set()
    for raw in payload.paths or []:
        path = str(raw or '').strip()
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    if len(paths) > 80:
        raise HTTPException(status_code=400, detail='Too many paths (max 80)')

    restricted_view = is_restricted_horizon_artist(user, access_role)
    assets_by_path = get_visible_horizon_media_assets_by_paths(
        db,
        project_id,
        paths,
        user=user,
        access_role=access_role,
    )
    resolved_items = []
    videos = []
    for path in paths:
        asset = assets_by_path.get(path.strip('/'))
        full_path = None
        if asset is not None:
            full_path, _cache_key, _storage_scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
        elif not restricted_view:
            full_path, _cache_key = resolve_media_full_path(path, project_id, storage_scope='project')

        if not full_path or not full_path.exists() or not full_path.is_file():
            resolved_items.append({'path': path, 'missing': True})
            continue

        stat = full_path.stat()
        ext = full_path.suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            videos.append((full_path, stat))
        resolved_items.append({
            'path': path,
            'asset': asset,
            'full_path': full_path,
            'stat': stat,
            'ext': ext,
        })

    durations = probe_cached_video_durations(videos, probe=get_video_duration_quick)
    items = []
    for resolved in resolved_items:
        if resolved.get('missing'):
            items.append(resolved)
            continue
        path = resolved['path']
        asset = resolved['asset']
        full_path = resolved['full_path']
        stat = resolved['stat']
        ext = resolved['ext']
        duration = durations.get(full_path) if ext in VIDEO_EXTENSIONS else None
        if isinstance(duration, Exception):
            items.append({'path': path, 'error': 'Unable to inspect file'})
            continue
        items.append(attach_canonical_media_identity({
            'path': path,
            'file_path': path,
            'name': full_path.name,
            'extension': ext.lstrip('.'),
            'size': stat.st_size,
            'size_formatted': format_size(stat.st_size),
            'created_at': getattr(stat, 'st_birthtime', stat.st_ctime),
            'modified_at': stat.st_mtime,
            'is_video': ext in VIDEO_EXTENSIONS,
            'is_image': ext in IMAGE_EXTENSIONS,
            'duration': duration,
            'duration_formatted': format_duration_label(duration) if duration else None,
        }, media_asset_id=asset.id if asset is not None else None))
    return {'items': items}


@router.post('/api/horizons/projects/{project_id}/thumbnail/select')
def select_horizons_entity_thumbnail(project_id: str, payload: HorizonsEntityThumbnailSelectRequest, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user, access_role, _project = _require_horizons_editor(project_id, vueio_session, db)
    try:
        entity_type, entity_path = normalize_horizon_thumbnail_entity(payload.entity_type, payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid thumbnail target') from exc
    entity_path = _authorize_thumbnail_mutation(db, project_id, user, access_role, entity_type, entity_path)
    require_user_file_browser_read_access(user, payload.source_path)
    source_path, full_path, _thumb_path, resolved_scope, cache_key = _resolve_horizons_thumbnail_source(
        db,
        project_id,
        payload.source_path,
        storage_scope='media_root',
    )

    existing = get_horizon_entity_thumbnail_record(project_id, entity_type, entity_path)
    if existing and str(existing.get('mode') or '').strip().lower() == 'uploaded':
        old_upload_name = str(existing.get('upload_name') or '').strip()
        old_upload_path = get_horizon_entity_upload_path(old_upload_name)
        if old_upload_name and old_upload_path.exists():
            try:
                old_upload_path.unlink()
            except Exception:
                pass

    set_horizon_entity_thumbnail_record(project_id, entity_type, {
        'mode': 'source',
        'source_path': source_path,
        'storage_scope': 'media_root',
        'updated_at': time.time(),
    }, entity_path)
    if entity_type == 'project':
        _set_project_thumbnail_marker(db, project_id)
        if full_path.suffix.lower() in VIDEO_EXTENSIONS:
            poster_path = delivery_poster_cache_path_for_identity(cache_key) if cache_key else delivery_poster_cache_path_for_media(project_id, source_path, full_path, storage_scope=resolved_scope)
            queue_thumbnail_generation(full_path, poster_path, width=DELIVERY_POSTER_WIDTH)
    return {'status': 'success', 'entity_type': entity_type, 'path': entity_path, 'source_path': source_path}


@router.post('/api/horizons/projects/{project_id}/thumbnail/upload')
async def upload_horizons_project_thumbnail(
    project_id: str,
    file: UploadFile = File(...),
    entity_type: str = Form('project'),
    path: str | None = Form(None),
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    user, access_role, _project = _require_horizons_editor(project_id, vueio_session, db)
    try:
        normalized_type, normalized_path = normalize_horizon_thumbnail_entity(entity_type, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid thumbnail target') from exc
    normalized_path = _authorize_thumbnail_mutation(db, project_id, user, access_role, normalized_type, normalized_path)
    filename = file.filename or 'thumbnail.jpg'
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS and not str(file.content_type or '').startswith('image/'):
        raise HTTPException(status_code=400, detail='Upload must be an image')

    contents = await read_bounded_upload(
        file,
        max_bytes=MAX_CUSTOM_THUMBNAIL_BYTES,
        too_large_detail='Thumbnail image is too large',
    )
    require_valid_image(contents, detail='Thumbnail image is invalid')

    existing = get_horizon_entity_thumbnail_record(project_id, normalized_type, normalized_path)
    if existing and str(existing.get('mode') or '').strip().lower() == 'uploaded':
        old_upload_name = str(existing.get('upload_name') or '').strip()
        old_upload_path = get_horizon_entity_upload_path(old_upload_name)
        if old_upload_name and old_upload_path.exists():
            try:
                old_upload_path.unlink()
            except Exception:
                pass

    upload_name = build_horizon_entity_upload_name(project_id, normalized_type, normalized_path, filename)
    upload_path = get_horizon_entity_upload_path(upload_name)
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    with open(upload_path, 'wb') as handle:
        handle.write(contents)

    set_horizon_entity_thumbnail_record(project_id, normalized_type, {
        'mode': 'uploaded',
        'upload_name': upload_name,
        'updated_at': time.time(),
    }, normalized_path)
    if normalized_type == 'project':
        _set_project_thumbnail_marker(db, project_id)
    return {'status': 'success', 'entity_type': normalized_type, 'path': normalized_path, 'upload_name': upload_name}


@router.head('/api/horizons/projects/{project_id}/thumbnail/uploaded')
@router.get('/api/horizons/projects/{project_id}/thumbnail/uploaded')
def get_uploaded_horizons_project_thumbnail(project_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    _user, _access_role, _project = _require_horizons_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    thumb_path = settings.thumbnail_dir / f'project_{project_id}.jpg'
    if thumb_path.exists():
        return FileResponse(thumb_path, media_type='image/jpeg')
    raise HTTPException(status_code=404, detail='No uploaded thumbnail')


@router.head('/api/horizons/projects/{project_id}/thumbnail/resolved')
@router.get('/api/horizons/projects/{project_id}/thumbnail/resolved')
def get_resolved_horizons_project_thumbnail(
    project_id: str,
    entity_type: str = 'project',
    path: str | None = None,
    share_id: str | None = None,
    share_token: str | None = None,
    cached_only: bool = False,
    variant: str | None = None,
    vueio_session: str | None = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, access_role, project = _resolve_horizons_thumbnail_viewer(project_id, vueio_session, x_vueio_agent_key, share_id, share_token, entity_type, path, db)
    return resolve_horizon_entity_thumbnail_response(
        db,
        project_id,
        entity_type,
        path,
        user=user,
        access_role=access_role,
        project=project,
        queue_missing=not cached_only,
        delivery_poster=_is_delivery_thumbnail_variant(variant),
    )


@router.post('/api/horizons/projects/{project_id}/folder-zip')
def download_horizons_project_folder_zip(project_id: str, data: HorizonsFolderZipRequest, background_tasks: BackgroundTasks, request: Request, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    if not data.path:
        raise HTTPException(status_code=400, detail='No path provided')
    user, access_role, _project = _require_horizons_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    entries = collect_zip(HorizonsProjectAuthPolicy(db, project_id, user, access_role), [data.path])
    filename = data.filename or Path(data.path).name
    return serve_zip_entries(
        entries,
        filename,
        background_tasks,
        db,
        request=request,
        audit=DownloadAuditSpec({
            'user': user,
            'source': 'app',
            'project_id': project_id,
            'event_type': 'download_folder_zip',
            'resource_type': 'project_folder',
            'resource_id': data.path,
            'resource_name': Path(data.path).name,
            'filename': filename,
            'paths': [data.path],
            'metadata': {'access_role': access_role},
        }),
    )


@router.get('/api/horizons/projects/{project_id}/shot-registry')
def get_horizons_project_shot_registry(project_id: str, tracker_name: str | None = None, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role, _project = _require_horizons_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    entries = list_horizon_shot_registry_entries(db, project_id, tracker_name=tracker_name, user=user, access_role=access_role)
    return {'entries': entries}
