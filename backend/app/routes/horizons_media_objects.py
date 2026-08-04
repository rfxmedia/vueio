from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, File, Header, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth import get_request_user
from app.services.horizons_fresh import (
    can_access_horizon_media_asset_id,
    can_access_horizon_shot_version_id,
    require_horizon_project_access,
)
from app.services.media_serving import (
    DownloadAuditSpec,
    HlsRouteBuilder,
    get_object_file_info,
    get_object_hls_asset,
    get_object_hls_manifest,
    get_object_hls_status,
    get_object_thumbnail,
    media_target,
    serve_download,
    set_object_thumbnail,
    stream_object_file,
)
from app.services.project_content_gateway import object_payload_tuple, resolve_horizons_object_auth
from app.services.share_access import _resolve_horizons_media_target_by_refs

router = APIRouter(tags=['horizons-media-objects'])


def _auth_ctx(vueio_session: str | None, x_vueio_agent_key: str | None):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    return user, auth_mode


def _require_horizons_media_viewer(project_id: str, vueio_session: str | None, x_vueio_agent_key: str | None, db: Session):
    user, auth_mode = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    return user, access_role


def _require_horizons_media_editor(project_id: str, vueio_session: str | None, x_vueio_agent_key: str | None, db: Session):
    user, auth_mode = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    return user, access_role


def _resolve_object_target(db: Session, project_id: str, *, asset_id: str | None = None, version_id: str | None = None, detail: str, user=None, access_role: str | None = None):
    full_path, cache_key, storage_scope, resolved_asset_id, canonical_path = _resolve_horizons_media_target_by_refs(
        db,
        project_id,
        horizons_media_asset_id=asset_id,
        horizons_shot_version_id=version_id,
    )
    if not canonical_path or not resolved_asset_id:
        raise HTTPException(status_code=404, detail=detail)
    if user is not None:
        if version_id:
            is_visible = can_access_horizon_shot_version_id(
                db,
                project_id,
                version_id,
                user=user,
                access_role=access_role,
            )
        else:
            is_visible = can_access_horizon_media_asset_id(
                db,
                project_id,
                resolved_asset_id,
                user=user,
                access_role=access_role,
            )
        if not is_visible:
            raise HTTPException(status_code=404, detail=detail)
    return full_path, cache_key, storage_scope, resolved_asset_id, canonical_path


def _build_horizons_object_payload(
    db: Session,
    project_id: str,
    *,
    asset_id: str | None = None,
    version_id: str | None = None,
    detail: str,
    user=None,
    access_role: str | None = None,
):
    return object_payload_tuple(resolve_horizons_object_auth(
        db,
        project_id,
        asset_id=asset_id,
        version_id=version_id,
        detail=detail,
        user=user,
        access_role=access_role,
    ))


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/file-info')
def get_horizons_media_asset_file_info(project_id: str, asset_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_file_info(lambda: _build_horizons_object_payload(
        db,
        project_id,
        asset_id=asset_id,
        detail='Horizons media asset not found',
        user=user,
        access_role=access_role,
    ))


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/stream')
@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/file')
def stream_horizons_media_asset(project_id: str, asset_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return stream_object_file(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            asset_id=asset_id,
            detail='Horizons media asset not found',
            user=user,
            access_role=access_role,
        ),
        db,
        not_found_detail='Horizons media asset file not found',
    )


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/hls/status')
def hls_status_horizons_media_asset(project_id: str, asset_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_status(lambda: _build_horizons_object_payload(
        db,
        project_id,
        asset_id=asset_id,
        detail='Horizons media asset not found',
        user=user,
        access_role=access_role,
    ), db)


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/hls/manifest')
def hls_manifest_horizons_media_asset(project_id: str, asset_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_manifest(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            asset_id=asset_id,
            detail='Horizons media asset not found',
            user=user,
            access_role=access_role,
        ),
        db,
        build_asset_url=HlsRouteBuilder(f'/api/horizons/projects/{project_id}/media-assets/{asset_id}/hls/asset'),
    )


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/hls/asset/{asset_path:path}')
def hls_asset_horizons_media_asset(project_id: str, asset_id: str, asset_path: str, hls_generation: str | None = None, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_asset(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            asset_id=asset_id,
            detail='Horizons media asset not found',
            user=user,
            access_role=access_role,
        ),
        asset_path=asset_path,
        build_asset_url=HlsRouteBuilder(f'/api/horizons/projects/{project_id}/media-assets/{asset_id}/hls/asset'),
        hls_generation=hls_generation,
    )


@router.head('/api/horizons/projects/{project_id}/media-assets/{asset_id}/thumbnail')
@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/thumbnail')
def thumbnail_horizons_media_asset(project_id: str, asset_id: str, cached_only: bool = False, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_thumbnail(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            asset_id=asset_id,
            detail='Horizons media asset not found',
            user=user,
            access_role=access_role,
        ),
        db,
        not_found_detail='Horizons media asset file not found',
        queue_missing=not cached_only,
    )


@router.post('/api/horizons/projects/{project_id}/media-assets/{asset_id}/thumbnail')
async def set_horizons_media_asset_thumbnail(project_id: str, asset_id: str, file: UploadFile = File(...), vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_editor(project_id, vueio_session, x_vueio_agent_key, db)
    return await set_object_thumbnail(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            asset_id=asset_id,
            detail='Horizons media asset not found',
            user=user,
            access_role=access_role,
        ),
        file=file,
        not_found_detail='Horizons media asset file not found',
    )


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/download')
def download_horizons_media_asset(project_id: str, asset_id: str, request: Request, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    full_path, _cache_key, payload = _build_horizons_object_payload(
        db,
        project_id,
        asset_id=asset_id,
        detail='Horizons media asset not found',
        user=user,
        access_role=access_role,
    )
    return serve_download(
        media_target(full_path, _cache_key, metadata_payload=payload),
        db,
        request=request,
        audit=DownloadAuditSpec({
            'user': user,
            'source': 'app',
            'project_id': project_id,
            'event_type': 'download_file',
            'resource_type': 'media_asset',
            'resource_id': asset_id,
            'resource_name': payload.get('name') or (full_path.name if full_path else asset_id),
            'filename': full_path.name if full_path else None,
            'paths': [payload.get('path') or ''],
            'size_bytes': full_path.stat().st_size if full_path and full_path.is_file() else None,
            'metadata': {'access_role': access_role},
        }),
        not_found_detail='Horizons media asset file not found',
        audit_before_exists=True,
    )


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/file-info')
def get_horizons_shot_version_file_info(project_id: str, version_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_file_info(lambda: _build_horizons_object_payload(
        db,
        project_id,
        version_id=version_id,
        detail='Horizons shot version not found',
        user=user,
        access_role=access_role,
    ))


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/stream')
@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/file')
def stream_horizons_shot_version(project_id: str, version_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return stream_object_file(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            version_id=version_id,
            detail='Horizons shot version not found',
            user=user,
            access_role=access_role,
        ),
        db,
        not_found_detail='Horizons shot version file not found',
    )


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/hls/status')
def hls_status_horizons_shot_version(project_id: str, version_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_status(lambda: _build_horizons_object_payload(
        db,
        project_id,
        version_id=version_id,
        detail='Horizons shot version not found',
        user=user,
        access_role=access_role,
    ), db)


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/hls/manifest')
def hls_manifest_horizons_shot_version(project_id: str, version_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_manifest(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            version_id=version_id,
            detail='Horizons shot version not found',
            user=user,
            access_role=access_role,
        ),
        db,
        build_asset_url=HlsRouteBuilder(f'/api/horizons/projects/{project_id}/shot-versions/{version_id}/hls/asset'),
    )


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/hls/asset/{asset_path:path}')
def hls_asset_horizons_shot_version(project_id: str, version_id: str, asset_path: str, hls_generation: str | None = None, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_asset(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            version_id=version_id,
            detail='Horizons shot version not found',
            user=user,
            access_role=access_role,
        ),
        asset_path=asset_path,
        build_asset_url=HlsRouteBuilder(f'/api/horizons/projects/{project_id}/shot-versions/{version_id}/hls/asset'),
        hls_generation=hls_generation,
    )


@router.head('/api/horizons/projects/{project_id}/shot-versions/{version_id}/thumbnail')
@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/thumbnail')
def thumbnail_horizons_shot_version(project_id: str, version_id: str, cached_only: bool = False, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_thumbnail(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            version_id=version_id,
            detail='Horizons shot version not found',
            user=user,
            access_role=access_role,
        ),
        db,
        not_found_detail='Horizons shot version file not found',
        queue_missing=not cached_only,
    )


@router.post('/api/horizons/projects/{project_id}/shot-versions/{version_id}/thumbnail')
async def set_horizons_shot_version_thumbnail(project_id: str, version_id: str, file: UploadFile = File(...), vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_editor(project_id, vueio_session, x_vueio_agent_key, db)
    return await set_object_thumbnail(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            version_id=version_id,
            detail='Horizons shot version not found',
            user=user,
            access_role=access_role,
        ),
        file=file,
        not_found_detail='Horizons shot version file not found',
    )


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/download')
def download_horizons_shot_version(project_id: str, version_id: str, request: Request, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    full_path, _cache_key, payload = _build_horizons_object_payload(
        db,
        project_id,
        version_id=version_id,
        detail='Horizons shot version not found',
        user=user,
        access_role=access_role,
    )
    return serve_download(
        media_target(full_path, _cache_key, metadata_payload=payload),
        db,
        request=request,
        audit=DownloadAuditSpec({
            'user': user,
            'source': 'app',
            'project_id': project_id,
            'event_type': 'download_file',
            'resource_type': 'shot_version',
            'resource_id': version_id,
            'resource_name': payload.get('name') or (full_path.name if full_path else version_id),
            'filename': full_path.name if full_path else None,
            'paths': [payload.get('path') or ''],
            'size_bytes': full_path.stat().st_size if full_path and full_path.is_file() else None,
            'metadata': {'access_role': access_role},
        }),
        not_found_detail='Horizons shot version file not found',
        audit_before_exists=True,
    )
