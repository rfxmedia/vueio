from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.media_serving import (
    DownloadAuditSpec,
    HlsRouteBuilder,
    get_object_file_info,
    get_object_hls_asset,
    get_object_hls_manifest,
    get_object_hls_status,
    get_object_thumbnail,
    media_target_from_resolved,
    media_target,
    serve_download,
    serve_file,
    serve_hls_asset,
    serve_hls_manifest,
    serve_hls_status,
    serve_zip_entries,
    stream_object_file,
)
from app.services.project_content_gateway import (
    AuthorizedZipRequest,
    ContentRef,
    SharedMediaPolicy,
    SharedPagePolicy,
    SharedProjectFilePolicy,
    SharedProjectFolderPolicy,
    SharedProjectPolicy,
    build_metadata,
    object_payload_tuple,
    resolve_content,
    resolve_horizons_object_share,
    thumbnail_content,
)
from app.services.share_access import normalize_virtual_path, require_path_within_shared_root, resolve_shared_media_target, validate_share
from app.services.zip_utils import ZipFileIdentity, collect_boundary_zip_entries, new_zip_discovery_budget

router = APIRouter(tags=['share-media'])
settings = get_settings()



class ZipDownloadRequest(BaseModel):
    paths: List[str]
    filename: Optional[str] = 'download.zip'


def _validate_shared_horizons_object_share(share_id: str, share_token: str | None, db: Session) -> object:
    return validate_share(share_id, None, db, ['project', 'project-file', 'project-folder', 'tracker', 'page'], share_token=share_token, track_access=False)


def _validate_shared_media_share(share_id: str, share_token: str | None, db: Session):
    share = validate_share(
        share_id,
        None,
        db,
        ['file', 'folder', 'project-file', 'project-folder', 'project', 'page'],
        share_token=share_token,
        track_access=False,
    )
    return share


def _shared_auth_query(_share_token: str | None, extra: dict | None = None) -> str:
    return urlencode(dict(extra or {}))


def _build_shared_object_payload(share, db: Session, *, horizons_media_asset_id: str | None = None, horizons_shot_version_id: str | None = None):
    return object_payload_tuple(resolve_horizons_object_share(
        share,
        db,
        asset_id=horizons_media_asset_id,
        version_id=horizons_shot_version_id,
    ))


def _shared_media_ref(share, path: str, media_asset_id: str | None = None) -> ContentRef:
    return ContentRef(namespace='shared_media', share_id=share.id, project_id=share.project_id, path=path or '', media_asset_id=media_asset_id)


@router.get('/api/projects/shared/{share_id}/media-assets/{asset_id}/file-info')
def get_shared_media_asset_file_info(share_id: str, asset_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return get_object_file_info(lambda: _build_shared_object_payload(share, db, horizons_media_asset_id=asset_id))


@router.get('/api/projects/shared/{share_id}/media-assets/{asset_id}/file')
def stream_shared_media_asset(share_id: str, asset_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return stream_object_file(
        lambda: _build_shared_object_payload(share, db, horizons_media_asset_id=asset_id),
        db,
        not_found_detail='Horizons shared media asset file not found',
    )


@router.get('/api/projects/shared/{share_id}/media-assets/{asset_id}/hls/status')
def hls_status_shared_media_asset(share_id: str, asset_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return get_object_hls_status(lambda: _build_shared_object_payload(share, db, horizons_media_asset_id=asset_id), db)


@router.get('/api/projects/shared/{share_id}/media-assets/{asset_id}/hls/manifest')
def hls_manifest_shared_media_asset(share_id: str, asset_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    auth_query = _shared_auth_query(share_token)
    return get_object_hls_manifest(
        lambda: _build_shared_object_payload(share, db, horizons_media_asset_id=asset_id),
        db,
        build_asset_url=HlsRouteBuilder(f'/api/projects/shared/{share_id}/media-assets/{asset_id}/hls/asset', auth_query),
    )


@router.get('/api/projects/shared/{share_id}/media-assets/{asset_id}/hls/asset/{asset_path:path}')
def hls_asset_shared_media_asset(share_id: str, asset_id: str, asset_path: str, share_token: str | None = None, hls_generation: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    auth_query = _shared_auth_query(share_token)
    return get_object_hls_asset(
        lambda: _build_shared_object_payload(share, db, horizons_media_asset_id=asset_id),
        asset_path=asset_path,
        build_asset_url=HlsRouteBuilder(f'/api/projects/shared/{share_id}/media-assets/{asset_id}/hls/asset', auth_query),
        hls_generation=hls_generation,
    )


@router.get('/api/projects/shared/{share_id}/media-assets/{asset_id}/download')
def download_shared_media_asset(share_id: str, asset_id: str, request: Request, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    full_path, cache_key, payload = _build_shared_object_payload(share, db, horizons_media_asset_id=asset_id)
    return serve_download(
        media_target(full_path, cache_key, metadata_payload=payload),
        db,
        request=request,
        audit=DownloadAuditSpec({
            'source': 'share',
            'share_id': share.id,
            'project_id': share.project_id,
            'event_type': 'download_file',
            'resource_type': 'media_asset',
            'resource_id': asset_id,
            'resource_name': payload.get('name') or (full_path.name if full_path else asset_id),
            'filename': full_path.name if full_path else None,
            'paths': [payload.get('path') or ''],
            'size_bytes': full_path.stat().st_size if full_path and full_path.is_file() else None,
            'metadata': {'share_type': share.share_type},
        }),
        not_found_detail='Horizons shared media asset file not found',
        audit_before_exists=True,
    )


@router.head('/api/projects/shared/{share_id}/media-assets/{asset_id}/thumbnail')
@router.get('/api/projects/shared/{share_id}/media-assets/{asset_id}/thumbnail')
def get_shared_media_asset_thumbnail(share_id: str, asset_id: str, share_token: str | None = None, cached_only: bool = False, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return get_object_thumbnail(
        lambda: _build_shared_object_payload(share, db, horizons_media_asset_id=asset_id),
        db,
        not_found_detail='Horizons shared media asset file not found',
        queue_missing=not cached_only,
    )


@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/file-info')
def get_shared_shot_version_file_info(share_id: str, version_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return get_object_file_info(lambda: _build_shared_object_payload(share, db, horizons_shot_version_id=version_id))


@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/file')
def stream_shared_shot_version(share_id: str, version_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return stream_object_file(
        lambda: _build_shared_object_payload(share, db, horizons_shot_version_id=version_id),
        db,
        not_found_detail='Horizons shared shot version file not found',
    )


@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/hls/status')
def hls_status_shared_shot_version(share_id: str, version_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return get_object_hls_status(lambda: _build_shared_object_payload(share, db, horizons_shot_version_id=version_id), db)


@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/hls/manifest')
def hls_manifest_shared_shot_version(share_id: str, version_id: str, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    auth_query = _shared_auth_query(share_token)
    return get_object_hls_manifest(
        lambda: _build_shared_object_payload(share, db, horizons_shot_version_id=version_id),
        db,
        build_asset_url=HlsRouteBuilder(f'/api/projects/shared/{share_id}/shot-versions/{version_id}/hls/asset', auth_query),
    )


@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/hls/asset/{asset_path:path}')
def hls_asset_shared_shot_version(share_id: str, version_id: str, asset_path: str, share_token: str | None = None, hls_generation: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    auth_query = _shared_auth_query(share_token)
    return get_object_hls_asset(
        lambda: _build_shared_object_payload(share, db, horizons_shot_version_id=version_id),
        asset_path=asset_path,
        build_asset_url=HlsRouteBuilder(f'/api/projects/shared/{share_id}/shot-versions/{version_id}/hls/asset', auth_query),
        hls_generation=hls_generation,
    )


@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/download')
def download_shared_shot_version(share_id: str, version_id: str, request: Request, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    full_path, cache_key, payload = _build_shared_object_payload(share, db, horizons_shot_version_id=version_id)
    return serve_download(
        media_target(full_path, cache_key, metadata_payload=payload),
        db,
        request=request,
        audit=DownloadAuditSpec({
            'source': 'share',
            'share_id': share.id,
            'project_id': share.project_id,
            'event_type': 'download_file',
            'resource_type': 'shot_version',
            'resource_id': version_id,
            'resource_name': payload.get('name') or (full_path.name if full_path else version_id),
            'filename': full_path.name if full_path else None,
            'paths': [payload.get('path') or ''],
            'size_bytes': full_path.stat().st_size if full_path and full_path.is_file() else None,
            'metadata': {'share_type': share.share_type},
        }),
        not_found_detail='Horizons shared shot version file not found',
        audit_before_exists=True,
    )


@router.head('/api/projects/shared/{share_id}/shot-versions/{version_id}/thumbnail')
@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/thumbnail')
def get_shared_shot_version_thumbnail(share_id: str, version_id: str, share_token: str | None = None, cached_only: bool = False, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    return get_object_thumbnail(
        lambda: _build_shared_object_payload(share, db, horizons_shot_version_id=version_id),
        db,
        not_found_detail='Horizons shared shot version file not found',
        queue_missing=not cached_only,
    )


@router.get('/api/projects/shared/{share_id}/file-info')
def get_shared_file_info(share_id: str, path: str = '', share_token: str | None = None, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    return build_metadata(SharedMediaPolicy(db, share), _shared_media_ref(share, path, media_asset_id or horizons_media_asset_id))


@router.get('/api/projects/shared/{share_id}/file')
def stream_shared_file(share_id: str, path: str = '', share_token: str | None = None, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    resolved = resolve_content(SharedMediaPolicy(db, share), _shared_media_ref(share, path, media_asset_id or horizons_media_asset_id), purpose='stream')
    return serve_file(media_target_from_resolved(resolved), db)


@router.get('/api/projects/shared/{share_id}/hls/status')
def hls_status_shared_file(share_id: str, path: str = '', share_token: str | None = None, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    resolved = resolve_content(SharedMediaPolicy(db, share), _shared_media_ref(share, path, media_asset_id or horizons_media_asset_id), purpose='stream')
    return serve_hls_status(media_target_from_resolved(resolved), db)


@router.get('/api/projects/shared/{share_id}/hls/manifest')
def hls_manifest_shared_file(share_id: str, path: str = '', share_token: str | None = None, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    resolved_asset_id = media_asset_id or horizons_media_asset_id
    resolved = resolve_content(SharedMediaPolicy(db, share), _shared_media_ref(share, path, resolved_asset_id), purpose='stream')
    auth_query = _shared_auth_query(share_token, {'path': path, **({'media_asset_id': resolved_asset_id} if resolved_asset_id else {})})
    return serve_hls_manifest(
        media_target_from_resolved(resolved),
        db,
        build_asset_url=HlsRouteBuilder(f'/api/projects/shared/{share_id}/hls/asset', auth_query),
    )


@router.get('/api/projects/shared/{share_id}/hls/asset/{asset_path:path}')
def hls_asset_shared_file(share_id: str, asset_path: str, path: str = '', share_token: str | None = None, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, hls_generation: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    resolved_asset_id = media_asset_id or horizons_media_asset_id
    resolved = resolve_content(SharedMediaPolicy(db, share), _shared_media_ref(share, path, resolved_asset_id), purpose='stream')
    auth_query = _shared_auth_query(share_token, {'path': path, **({'media_asset_id': resolved_asset_id} if resolved_asset_id else {})})
    return serve_hls_asset(
        media_target_from_resolved(resolved),
        asset_path=asset_path,
        build_asset_url=HlsRouteBuilder(f'/api/projects/shared/{share_id}/hls/asset', auth_query),
        hls_generation=hls_generation,
    )


@router.get('/api/projects/shared/{share_id}/download')
def download_shared_file_raw(share_id: str, request: Request, path: str = '', share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    resolved = resolve_content(SharedMediaPolicy(db, share), _shared_media_ref(share, path), purpose='download')
    full_path = resolved.full_path
    return serve_download(
        media_target_from_resolved(resolved),
        db,
        request=request,
        audit=DownloadAuditSpec({
            'source': 'share',
            'share_id': share.id,
            'project_id': share.project_id,
            'event_type': 'download_file',
            'resource_type': share.share_type or 'shared_file',
            'resource_id': path or share.path,
            'resource_name': full_path.name,
            'filename': full_path.name,
            'paths': [path or share.path or ''],
            'size_bytes': full_path.stat().st_size if full_path.is_file() else None,
            'metadata': {'share_type': share.share_type},
        }),
    )


@router.post('/api/projects/shared/{share_id}/download-zip')
def download_shared_zip(share_id: str, data: ZipDownloadRequest, background_tasks: BackgroundTasks, request: Request, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    if not data.paths:
        raise HTTPException(status_code=400, detail='No paths provided')
    if share.project_id:
        if share.share_type == 'project-folder':
            policy = SharedProjectFolderPolicy(db, share)
        elif share.share_type == 'project-file':
            policy = SharedProjectFilePolicy(db, share)
        elif share.share_type == 'page':
            policy = SharedPagePolicy(db, share)
        else:
            policy = SharedProjectPolicy(db, share)
        budget = new_zip_discovery_budget()
        refs = policy.assert_can_zip_roots(data.paths)
        virtual_entries = policy.collect_zip_entries(AuthorizedZipRequest(refs=refs, budget=budget, discovered_identities=set()))
        if not virtual_entries:
            raise HTTPException(status_code=404, detail='No files found')
        resolved_audit_paths = [ref.path for ref in refs]
    else:
        budget = new_zip_discovery_budget()
        discovered_identities: set[ZipFileIdentity] = set()
        full_paths: List[Path] = []
        virtual_entries = []
        for candidate in data.paths:
            normalized_candidate = normalize_virtual_path(candidate or share.path or '', allow_empty=True)
            if share.share_type in {'folder'} and share.path:
                normalized_candidate = require_path_within_shared_root(share.path, normalized_candidate)
            if share.share_type in {'file'} and share.path:
                shared_file = normalize_virtual_path(share.path, allow_empty=False)
                if normalized_candidate != shared_file:
                    raise HTTPException(status_code=403, detail='Access denied - can only access shared file')
            full_path, _cache_key = resolve_shared_media_target(share, normalized_candidate, db=db)
            full_paths.append(full_path)
        for full_path in full_paths:
            virtual_entries.extend(collect_boundary_zip_entries(
                full_path,
                full_path.name,
                physical_root=settings.MEDIA_ROOT,
                budget=budget,
                discovered_identities=discovered_identities,
            ))
        if not virtual_entries:
            raise HTTPException(status_code=404, detail='No files found')
        resolved_audit_paths = [str(path) for path in full_paths]
    filename = data.filename or 'download.zip'
    return serve_zip_entries(
        virtual_entries,
        filename,
        background_tasks,
        db,
        request=request,
        audit=DownloadAuditSpec({
            'source': 'share',
            'share_id': share.id,
            'project_id': share.project_id,
            'event_type': 'download_zip',
            'resource_type': share.share_type or 'shared_zip',
            'resource_id': share.path,
            'resource_name': filename,
            'filename': filename,
            'paths': data.paths,
            'metadata': {'share_type': share.share_type, 'resolved_paths': resolved_audit_paths + [str(entry.path) for entry in virtual_entries]},
        }),
    )


@router.head('/api/projects/shared/{share_id}/thumbnail')
@router.get('/api/projects/shared/{share_id}/thumbnail')
def get_shared_thumbnail(share_id: str, path: str = '', share_token: str | None = None, cached_only: bool = False, media_asset_id: str | None = None, horizons_media_asset_id: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_media_share(share_id, share_token, db)
    return thumbnail_content(SharedMediaPolicy(db, share), _shared_media_ref(share, path, media_asset_id or horizons_media_asset_id), db, cached_only=cached_only)
