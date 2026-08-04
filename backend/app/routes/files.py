from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import MediaAsset, TranscodeJob
from app.runtime_state import cleanup_old_transcode_entries, transcode_progress
from app.services.auth import get_request_user, get_user_from_session, require_admin
from app.services.file_access import (
    filter_items_by_permission,
    require_file_browser_access,
    require_file_browser_read_access,
    require_user_file_browser_read_access,
)
from app.services.horizons_fresh import require_horizon_project_access
from app.services.media_serving import MAX_CUSTOM_THUMBNAIL_BYTES, DownloadAuditSpec, media_target, serve_download, serve_thumbnail, serve_zip_entries
from app.services.upload_payloads import read_bounded_upload, require_valid_image
from app.services.project_access import require_project_auth, resolve_authorized_legacy_project_media_target
from app.services.project_content_gateway import AuthorizedZipRequest, NasAuthPolicy
from app.services.projects import get_project_dir
from app.services.media import (
    IMAGE_EXTENSIONS,
    format_size,
    generate_thumbnail,
    get_folder_item_count,
    get_safe_path,
    is_video,
    needs_transcode,
)
from app.services.media_metadata import get_cached_video_info
from app.services.media_assets import merge_media_asset_metadata, register_media_asset
from app.services.media_resolution import folder_thumbnail_cache_path, generated_thumbnail_cache_path_for_identity, resolve_media_asset_path, resolve_media_target, thumbnail_cache_path_for_browser
from app.services.share_access import _resolve_horizons_media_target_by_refs, is_horizons_share_project, require_path_within_shared_root, resolve_shared_horizons_object_target, resolve_shared_media_target, validate_share
from app.services.uploads import UPLOAD_SCOPE_SHARED, get_latest_upload_metadata
from app.services.zip_utils import new_zip_discovery_budget

router = APIRouter(tags=['files'])
settings = get_settings()

HIDDEN_FOLDERS = settings.hidden_storage_folders


class ZipDownloadRequest(BaseModel):
    paths: List[str]
    filename: Optional[str] = 'download.zip'


@router.get('/')
def health():
    return {'status': 'ok'}


def require_nas_thumbnail_mutation_access(vueio_session: str | None, *paths: str) -> dict:
    user = require_admin(vueio_session)
    for path in paths:
        require_user_file_browser_read_access(user, path)
    return user


@router.get('/api/files')
def list_files(
    path: str = '',
    share_root: str = '',
    include_counts: bool = False,
    share_id: str | None = None,
    share_token: str | None = None,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    user = get_user_from_session(vueio_session)

    if share_id:
        share = validate_share(share_id, None, db, ['folder'], share_token=share_token, track_access=False)
        if not share.is_folder:
            raise HTTPException(status_code=400, detail='Share is not a folder')
        share_root = share.path or ''
        user = None
        if share_root and not path:
            path = share_root
        if share_root and path:
            path = require_path_within_shared_root(share_root, path)
    else:
        require_file_browser_access(vueio_session, path if path else '')

    target = get_safe_path(path if path else share_root)
    if not target.exists():
        raise HTTPException(status_code=404, detail='Path not found')
    if not target.is_dir():
        raise HTTPException(status_code=400, detail='Not a directory')

    items = []
    for entry in target.iterdir():
        if entry.is_symlink() or entry.name.startswith('.') or entry.name in HIDDEN_FOLDERS:
            continue

        rel_path = str(entry.relative_to(settings.MEDIA_ROOT))
        stat = entry.stat()
        if entry.is_dir():
            has_custom_thumb = folder_thumbnail_cache_path(rel_path).exists()
            items.append({
                'name': entry.name,
                'path': rel_path,
                'type': 'folder',
                'file_count': get_folder_item_count(entry) if include_counts else None,
                'mtime': stat.st_mtime,
                'ctime': stat.st_ctime,
                'custom_thumbnail': has_custom_thumb,
            })
        elif is_video(entry):
            items.append({
                'name': entry.name,
                'path': rel_path,
                'type': 'video',
                'size': stat.st_size,
                'size_formatted': format_size(stat.st_size),
                'mtime': stat.st_mtime,
                'ctime': stat.st_ctime,
                'extension': entry.suffix.lower().lstrip('.'),
                'needs_transcode': needs_transcode(entry),
            })
        else:
            ext = entry.suffix.lower()
            item = {
                'name': entry.name,
                'path': rel_path,
                'type': 'image' if ext in IMAGE_EXTENSIONS else 'file',
                'size': stat.st_size,
                'size_formatted': format_size(stat.st_size),
                'mtime': stat.st_mtime,
                'ctime': stat.st_ctime,
                'extension': ext.lstrip('.'),
            }
            if ext in IMAGE_EXTENSIONS:
                item['is_image'] = True
            items.append(item)

    if not share_root and user:
        items = filter_items_by_permission(user, items)

    for item in items:
        if item.get('type') == 'folder':
            continue
        asset = register_media_asset(db, None, item.get('path') or '', storage_scope='media_root', commit=False)
        if asset:
            item.update(merge_media_asset_metadata(item, asset))
        item.update(get_latest_upload_metadata(db, scope_type=UPLOAD_SCOPE_SHARED, final_path=item.get('path') or '') or {})

    db.commit()

    items.sort(key=lambda item: (item['type'] != 'folder', item['name'].lower()))
    parts = path.strip('/').split('/') if path else []
    share_parts = share_root.strip('/').split('/') if share_root else []
    if share_root:
        breadcrumbs = [{'name': share_parts[-1] if share_parts else 'Shared', 'path': share_root}]
        if path.startswith(share_root) and len(path) > len(share_root):
            extra = path[len(share_root):].strip('/')
            current = share_root
            for part in extra.split('/'):
                if part:
                    current = f'{current}/{part}'
                    breadcrumbs.append({'name': part, 'path': current})
    else:
        breadcrumbs = [{'name': 'Home', 'path': ''}]
        current = ''
        for part in parts:
            if part:
                current = f'{current}/{part}' if current else part
                breadcrumbs.append({'name': part, 'path': current})

    payload = {'path': path, 'items': items, 'breadcrumbs': breadcrumbs, 'share_root': share_root}
    if share_id:
        payload['_share_allow_upload'] = bool(share.allow_upload)
    return payload


@router.get('/api/video-info')
def video_info(path: str, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    require_file_browser_read_access(vueio_session, path)
    file_path = get_safe_path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')

    resolved_asset_id = media_asset_id or horizons_media_asset_id
    if resolved_asset_id:
        asset = db.query(MediaAsset).filter(MediaAsset.id == resolved_asset_id).first()
        if (
            not asset
            or asset.project_id != '__media_root__'
            or asset.storage_scope != 'media_root'
            or asset.file_path != path.strip().strip('/')
        ):
            raise HTTPException(status_code=404, detail='Media asset not found')
        resolved_path, cache_key, _scope = resolve_media_asset_path(asset, db=db)
        if not resolved_path:
            raise HTTPException(status_code=410, detail='Media asset is unavailable')
        file_path = resolved_path
    else:
        cache_key = None

    info = get_cached_video_info(
        db,
        file_path,
        path,
        storage_scope='media_root',
        media_asset_id=resolved_asset_id,
        cache_identity=cache_key,
    )
    try:
        stat = file_path.stat()
        created_at = getattr(stat, 'st_birthtime', stat.st_mtime)
        info['created_at'] = created_at
        info['file_size'] = stat.st_size
    except Exception:
        info['created_at'] = None
        info['file_size'] = 0
    return info


@router.head('/api/thumbnail')
@router.get('/api/thumbnail')
def get_thumbnail(path: str, refresh: int | None = None, cached_only: bool = False, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    require_file_browser_read_access(vueio_session, path)
    file_path = get_safe_path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')

    resolved_asset_id = media_asset_id or horizons_media_asset_id
    cache_key = None
    if resolved_asset_id:
        asset = db.query(MediaAsset).filter(MediaAsset.id == resolved_asset_id).first()
        if (
            not asset
            or asset.project_id != '__media_root__'
            or asset.storage_scope != 'media_root'
            or asset.file_path != path.strip().strip('/')
        ):
            raise HTTPException(status_code=404, detail='Media asset not found')
        resolved_path, cache_key, _scope = resolve_media_asset_path(asset, db=db)
        if not resolved_path:
            raise HTTPException(status_code=410, detail='Media asset is unavailable')
        file_path = resolved_path

    thumb_path = generated_thumbnail_cache_path_for_identity(cache_key) if cache_key else thumbnail_cache_path_for_browser(path)
    if refresh and thumb_path.exists():
        try:
            thumb_path.unlink()
        except Exception:
            pass

    if not cache_key:
        _resolved_path, cache_key, _storage_scope = resolve_media_target(path, storage_scope='media_root')
    return serve_thumbnail(
        media_target(file_path, cache_key),
        thumb_path=thumb_path,
        purge_empty_cache=True,
        cached_only=cached_only,
    )


@router.delete('/api/thumbnail')
def delete_thumbnail(path: str, vueio_session: str | None = Cookie(None)):
    require_nas_thumbnail_mutation_access(vueio_session, path)
    thumb_path = thumbnail_cache_path_for_browser(path)
    deleted = False
    if thumb_path.exists():
        thumb_path.unlink()
        deleted = True

    file_path = get_safe_path(path)
    if file_path.exists():
        success = generate_thumbnail(file_path, thumb_path)
        if success:
            return {'status': 'regenerated'}
        return {'status': 'deleted_but_regeneration_failed', 'message': 'Video may still be corrupted or rendering'}

    return {'status': 'deleted' if deleted else 'not_found'}


@router.post('/api/folder-thumbnail/upload')
async def upload_folder_thumbnail(
    target_path: str = Form(...),
    file: UploadFile = File(...),
    vueio_session: str | None = Cookie(None),
):
    require_nas_thumbnail_mutation_access(vueio_session, target_path)
    folder_path = get_safe_path(target_path)
    if not folder_path.is_dir():
        raise HTTPException(status_code=400, detail='Target must be a folder')

    thumb_path = folder_thumbnail_cache_path(target_path)
    contents = await read_bounded_upload(
        file,
        max_bytes=MAX_CUSTOM_THUMBNAIL_BYTES,
        too_large_detail='Thumbnail image is too large',
    )
    require_valid_image(contents, detail='Thumbnail image is invalid')
    with open(thumb_path, 'wb') as handle:
        handle.write(contents)
    return {'status': 'success', 'thumbnail_path': str(thumb_path)}


@router.post('/api/folder-thumbnail/set')
def set_folder_thumbnail_from_nas(target_path: str, source_path: str, vueio_session: str | None = Cookie(None)):
    require_nas_thumbnail_mutation_access(vueio_session, target_path, source_path)
    folder_path = get_safe_path(target_path)
    source_file = get_safe_path(source_path)
    if not folder_path.is_dir():
        raise HTTPException(status_code=400, detail='Target must be a folder')
    if not source_file.exists():
        raise HTTPException(status_code=404, detail='Source file not found')

    thumb_path = folder_thumbnail_cache_path(target_path)
    if generate_thumbnail(source_file, thumb_path):
        return {'status': 'success', 'thumbnail_path': str(thumb_path)}
    raise HTTPException(status_code=500, detail='Failed to generate thumbnail')


@router.head('/api/folder-thumbnail')
@router.get('/api/folder-thumbnail')
def get_folder_thumbnail(path: str, vueio_session: str | None = Cookie(None)):
    require_file_browser_read_access(vueio_session, path)
    thumb_path = folder_thumbnail_cache_path(path)
    if thumb_path.exists():
        return FileResponse(thumb_path, media_type='image/jpeg')
    raise HTTPException(status_code=404, detail='No custom thumbnail')


@router.get('/api/transcode-status')
def transcode_status(
    path: str | None = None,
    project_id: str | None = None,
    share_id: str | None = None,
    share_token: str | None = None,
    horizons_media_asset_id: str | None = None,
    horizons_shot_version_id: str | None = None,
    vueio_session: str | None = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    cleanup_old_transcode_entries()

    job_key = None

    if share_id:
        share = validate_share(share_id, None, db, ['file', 'folder', 'project-file', 'project-folder', 'project', 'tracker'], share_token=share_token, track_access=False)
        if is_horizons_share_project(share) and (horizons_media_asset_id or horizons_shot_version_id):
            _full_path, job_key, _storage_scope, _asset_id, _canonical_path = resolve_shared_horizons_object_target(
                share,
                db,
                horizons_media_asset_id=horizons_media_asset_id,
                horizons_shot_version_id=horizons_shot_version_id,
            )
        else:
            if not path:
                raise HTTPException(status_code=400, detail='Path is required')
            _full_path, job_key = resolve_shared_media_target(share, path, db=db)
    elif project_id and (horizons_media_asset_id or horizons_shot_version_id):
        user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
        require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
        _full_path, job_key, _storage_scope, _asset_id, _canonical_path = _resolve_horizons_media_target_by_refs(
            db,
            project_id,
            horizons_media_asset_id=horizons_media_asset_id,
            horizons_shot_version_id=horizons_shot_version_id,
        )
    elif project_id:
        if not path:
            raise HTTPException(status_code=400, detail='Path is required')
        if not (get_project_dir(project_id) / 'project.json').exists():
            raise HTTPException(status_code=409, detail='Horizons projects must use explicit media object refs')
        user = require_project_auth(project_id, vueio_session)
        full_path, resolved_job_key, _storage_scope = resolve_authorized_legacy_project_media_target(project_id, path, user)
        if not full_path:
            raise HTTPException(status_code=404, detail='File not found')
        job_key = resolved_job_key or path
    else:
        if not path:
            raise HTTPException(status_code=400, detail='Path is required')
        require_file_browser_read_access(vueio_session, path)
        full_path, resolved_job_key, _storage_scope = resolve_media_target(path, storage_scope='media_root')
        if not full_path:
            raise HTTPException(status_code=404, detail='File not found')
        job_key = resolved_job_key or path

    if not job_key:
        return {'status': 'none', 'progress': 0}
    if job_key in transcode_progress:
        return transcode_progress[job_key]
    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).first()
    if not job:
        return {'status': 'none', 'progress': 0}
    return {'status': job.status, 'progress': job.progress}


@router.get('/api/download')
def download_file(request: Request, path: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = require_file_browser_read_access(vueio_session, path)
    file_path = get_safe_path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return serve_download(
        media_target(file_path, None),
        db,
        request=request,
        audit=DownloadAuditSpec({
            'user': user,
            'source': 'app',
            'event_type': 'download_file',
            'resource_type': 'file',
            'resource_id': path,
            'resource_name': file_path.name,
            'filename': file_path.name,
            'paths': [path],
            'size_bytes': file_path.stat().st_size if file_path.is_file() else None,
        }),
    )


@router.post('/api/download-zip')
def download_zip(data: ZipDownloadRequest, background_tasks: BackgroundTasks, request: Request, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = require_file_browser_access(vueio_session)
    if not data.paths:
        raise HTTPException(status_code=400, detail='No paths provided')
    policy = NasAuthPolicy(user)
    refs = policy.assert_can_zip_roots(data.paths)
    entries = policy.collect_zip_entries(AuthorizedZipRequest(refs=refs, budget=new_zip_discovery_budget(), discovered_identities=set()))
    if not entries:
        raise HTTPException(status_code=404, detail='No files found')

    filename = data.filename or 'download.zip'
    return serve_zip_entries(
        entries,
        filename,
        background_tasks,
        db,
        request=request,
        audit=DownloadAuditSpec({
            'user': user,
            'source': 'app',
            'event_type': 'download_zip',
            'resource_type': 'file_zip',
            'resource_name': filename,
            'filename': filename,
            'paths': data.paths,
            'metadata': {'resolved_paths': [ref.path for ref in refs]},
        }),
    )
