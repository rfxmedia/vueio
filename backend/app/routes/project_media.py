from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.file_access import require_file_browser_read_access
from app.services.media import (
    DELIVERY_POSTER_WIDTH,
    IMAGE_EXTENSIONS,
    THUMBNAIL_WIDTH,
    VIDEO_EXTENSIONS,
    format_duration_label,
    format_size,
    get_video_duration_quick,
)
from app.services.hls_streaming import get_hls_thumbnail_source
from app.services.media_serving import DownloadAuditSpec, media_target, serve_thumbnail, serve_zip_entries
from app.services.media_resolution import (
    delivery_poster_cache_path_for_media,
    generated_thumbnail_cache_path_for_identity,
    resolve_project_content_target,
    thumbnail_cache_path_for_media,
)
from app.services.project_content_gateway import AuthorizedZipRequest, ContentRef, LegacyProjectAuthPolicy, thumbnail_content
from app.services.project_access import require_project_auth, resolve_authorized_legacy_project_media_target
from app.services.projects import get_project_dir, load_project
from app.services.share_access import _path_within_shared_root, is_horizons_share_project, resolve_project_thumbnail_target, validate_share
from app.services.zip_utils import new_zip_discovery_budget

settings = get_settings()
router = APIRouter(tags=['project-media'])


class BatchMediaInfoRequest(BaseModel):
    paths: list[str]
    project_id: Optional[str] = None


class FolderZipRequest(BaseModel):
    path: str
    filename: Optional[str] = None


def _validate_project_share(project_id: str, share_id: str | None, db: Session, allowed_types: list[str], share_token: str | None = None):
    if not share_id:
        return None
    share = validate_share(share_id, None, db, allowed_types, share_token=share_token, track_access=False)
    if share.project_id != project_id:
        raise HTTPException(status_code=403, detail='Access denied to this project')
    return share


def _is_legacy_project(project_id: str) -> bool:
    return (get_project_dir(project_id) / 'project.json').exists()


@router.post('/api/media-info/batch')
def batch_media_info(payload: BatchMediaInfoRequest, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
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

    project_id = (payload.project_id or '').strip() or None
    if project_id and not _is_legacy_project(project_id):
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')

    project_user = require_project_auth(project_id, vueio_session) if project_id else None

    items = []
    for path in paths:
        try:
            if project_id:
                full_path, _cache_key, _storage_scope = resolve_authorized_legacy_project_media_target(
                    project_id,
                    path,
                    project_user,
                )
            else:
                require_file_browser_read_access(vueio_session, path)
                from app.services.media import get_safe_path
                full_path = get_safe_path(path)
            if not full_path or not full_path.exists() or not full_path.is_file():
                items.append({'path': path, 'missing': True})
                continue
            stat = full_path.stat()
            ext = full_path.suffix.lower()
            duration = get_video_duration_quick(full_path) if ext in VIDEO_EXTENSIONS else None
            items.append({
                'path': path,
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
            })
        except HTTPException:
            raise
        except Exception:
            items.append({'path': path, 'error': 'Unable to inspect file'})
    return {'items': items}


@router.head('/api/project-thumbnail/{project_id}')
@router.get('/api/project-thumbnail/{project_id}')
def get_project_thumbnail(project_id: str, share_id: str | None = None, share_token: str | None = None, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    if share_id:
        share = _validate_project_share(project_id, share_id, db, ['project', 'project-folder', 'tracker'], share_token=share_token)
        if is_horizons_share_project(share):
            raise HTTPException(status_code=409, detail='Horizons shares must use dedicated /api/horizons routes')
    elif _is_legacy_project(project_id):
        require_project_auth(project_id, vueio_session)
    else:
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')
    thumb_path = settings.thumbnail_dir / f'project_{project_id}.jpg'
    if thumb_path.exists():
        return FileResponse(thumb_path, media_type='image/jpeg')
    raise HTTPException(status_code=404, detail='No uploaded thumbnail')


def _is_delivery_thumbnail_variant(variant: str | None) -> bool:
    return str(variant or '').strip().lower() in {'delivery', 'delivery_poster', 'poster'}


@router.head('/api/project-thumbnail/{project_id}/resolved')
@router.get('/api/project-thumbnail/{project_id}/resolved')
def get_project_thumbnail_resolved(project_id: str, share_id: str | None = None, share_token: str | None = None, cached_only: bool = False, variant: str | None = None, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    project_user = None
    if share_id:
        share = _validate_project_share(project_id, share_id, db, ['project', 'project-folder', 'tracker'], share_token=share_token)
        if is_horizons_share_project(share):
            raise HTTPException(status_code=409, detail='Horizons shares must use dedicated /api/horizons routes')
    elif _is_legacy_project(project_id):
        project_user = require_project_auth(project_id, vueio_session)
    else:
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')

    project = load_project(project_id)
    thumbnail_path = project.get('thumbnail_path')
    if not thumbnail_path:
        raise HTTPException(status_code=404, detail='No project thumbnail')

    if str(thumbnail_path).startswith('__uploaded_project_'):
        thumb_path = settings.thumbnail_dir / f'project_{project_id}.jpg'
        if thumb_path.exists():
            return FileResponse(thumb_path, media_type='image/jpeg')
        raise HTTPException(status_code=404, detail='No uploaded thumbnail')

    if project_user is not None:
        full_path, cache_key, _storage_scope = resolve_authorized_legacy_project_media_target(
            project_id,
            thumbnail_path,
            project_user,
        )
    else:
        full_path, cache_key, _storage_scope = resolve_project_content_target(project_id, thumbnail_path)
    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail='File not found')

    delivery_poster = _is_delivery_thumbnail_variant(variant)
    thumb_path = (
        delivery_poster_cache_path_for_media(project_id, thumbnail_path, full_path)
        if delivery_poster
        else thumbnail_cache_path_for_media(project_id, thumbnail_path, full_path)
    )
    preferred_source = None if delivery_poster else (get_hls_thumbnail_source(cache_key) if cache_key else None)
    return serve_thumbnail(
        media_target(full_path, cache_key),
        thumb_path=thumb_path,
        preferred_video_source=preferred_source,
        cached_only=cached_only,
        thumbnail_width=DELIVERY_POSTER_WIDTH if delivery_poster else THUMBNAIL_WIDTH,
    )


@router.head('/api/project-thumbnail/{project_id}/file')
@router.get('/api/project-thumbnail/{project_id}/file')
def get_project_file_thumbnail(project_id: str, path: str, share_id: str | None = None, share_token: str | None = None, cached_only: bool = False, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    if share_id:
        share = _validate_project_share(project_id, share_id, db, ['project', 'project-folder', 'project-file'], share_token=share_token)
        if is_horizons_share_project(share):
            raise HTTPException(status_code=409, detail='Horizons shares must use dedicated /api/horizons routes')
        if share.share_type == 'project-folder' and share.path and not _path_within_shared_root(share.path, path):
            raise HTTPException(status_code=403, detail='Access denied - path outside shared folder')
        if share.share_type == 'project-file' and share.path and path != share.path:
            raise HTTPException(status_code=403, detail='Access denied - can only access shared file')
        full_path, cache_key, storage_scope, asset_id = resolve_project_thumbnail_target(project_id, path, db=db)
    elif _is_legacy_project(project_id):
        user = require_project_auth(project_id, vueio_session)
        return thumbnail_content(
            LegacyProjectAuthPolicy(db, project_id, user, 'owner'),
            ContentRef(namespace='legacy_project', project_id=project_id, path=path),
            db,
            cached_only=cached_only,
        )
    else:
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')

    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail='File not found')

    if cache_key:
        thumb_path = generated_thumbnail_cache_path_for_identity(cache_key)
        preferred_source = get_hls_thumbnail_source(cache_key)
    elif asset_id:
        thumb_path = generated_thumbnail_cache_path_for_identity(f'asset:{asset_id}')
        preferred_source = get_hls_thumbnail_source(f'asset:{asset_id}')
    else:
        thumb_path = thumbnail_cache_path_for_media(project_id, path, full_path, storage_scope=storage_scope)
        preferred_source = None
    return serve_thumbnail(
        media_target(full_path, cache_key or (f'asset:{asset_id}' if asset_id else None)),
        thumb_path=thumb_path,
        preferred_video_source=preferred_source,
        cached_only=cached_only,
    )


@router.post('/api/projects/{project_id}/folder-zip')
def download_project_folder_zip(project_id: str, data: FolderZipRequest, background_tasks: BackgroundTasks, request: Request, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    if not data.path:
        raise HTTPException(status_code=400, detail='No path provided')
    if not _is_legacy_project(project_id):
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')
    user = require_project_auth(project_id, vueio_session)
    policy = LegacyProjectAuthPolicy(db, project_id, user, 'owner')
    refs = policy.assert_can_zip_roots([data.path])
    entries = policy.collect_zip_entries(AuthorizedZipRequest(refs=refs, budget=new_zip_discovery_budget(), discovered_identities=set()))
    if not entries:
        raise HTTPException(status_code=404, detail='No files found in folder')
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
        }),
    )
