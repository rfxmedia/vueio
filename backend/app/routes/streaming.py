from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import MediaAsset
from app.services.file_access import require_file_browser_read_access
from app.services.media_serving import HlsRouteBuilder, media_target, serve_file, serve_hls_asset, serve_hls_manifest, serve_hls_status
from app.services.media_resolution import resolve_media_asset_path, resolve_media_target
from app.services.project_access import require_project_auth, resolve_authorized_legacy_project_media_target
from app.services.projects import get_project_dir
from app.services.share_access import resolve_shared_media_target, validate_share

router = APIRouter(tags=['streaming'])


def _is_legacy_project(project_id: str) -> bool:
    return (get_project_dir(project_id) / 'project.json').exists()


def _resolve_stream_target(
    *,
    path: str,
    share_id: str | None,
    share_token: str | None,
    project_id: str | None,
    media_asset_id: str | None,
    vueio_session: str | None,
    db: Session,
):
    if media_asset_id and not share_id and not project_id:
        require_file_browser_read_access(vueio_session, path)
        asset = db.query(MediaAsset).filter(MediaAsset.id == media_asset_id).first()
        if (
            not asset
            or asset.project_id != '__media_root__'
            or asset.storage_scope != 'media_root'
            or asset.file_path != path.strip().strip('/')
        ):
            raise HTTPException(status_code=404, detail='Media asset not found')
        full_path, job_key, _scope = resolve_media_asset_path(asset, db=db)
        if not full_path:
            raise HTTPException(status_code=410, detail='Media asset is unavailable')
        return full_path, job_key

    if share_id:
        share = validate_share(share_id, None, db, ['file', 'folder', 'project-file', 'project-folder', 'project', 'tracker'], share_token=share_token, track_access=False)
        full_path, job_key = resolve_shared_media_target(share, path, db=db)
        return full_path, job_key

    if project_id:
        if not _is_legacy_project(project_id):
            raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')
        user = require_project_auth(project_id, vueio_session)
        full_path, job_key, _storage_scope = resolve_authorized_legacy_project_media_target(project_id, path, user)
        if not full_path or not full_path.exists():
            raise HTTPException(status_code=404, detail='File not found')
        return full_path, job_key or path

    require_file_browser_read_access(vueio_session, path)
    full_path, job_key, _storage_scope = resolve_media_target(path, storage_scope='media_root')
    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return full_path, job_key or path


@router.get('/api/stream')
def stream_video(
    path: str,
    share_id: str | None = None,
    share_token: str | None = None,
    project_id: str | None = None,
    media_asset_id: str | None = None,
    horizons_media_asset_id: str | None = None,
    vueio_session: str | None = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    full_path, transcode_key = _resolve_stream_target(
        path=path,
        share_id=share_id,
        share_token=share_token,
        project_id=project_id,
        media_asset_id=media_asset_id or horizons_media_asset_id,
        vueio_session=vueio_session,
        db=db,
    )
    return serve_file(media_target(full_path, transcode_key or path), db)


@router.get('/api/hls/status')
def hls_status(
    path: str,
    project_id: str | None = None,
    media_asset_id: str | None = None,
    horizons_media_asset_id: str | None = None,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    full_path, job_key = _resolve_stream_target(
        path=path,
        share_id=None,
        share_token=None,
        project_id=project_id,
        media_asset_id=media_asset_id or horizons_media_asset_id,
        vueio_session=vueio_session,
        db=db,
    )
    return serve_hls_status(media_target(full_path, job_key), db)


@router.get('/api/hls/manifest')
def hls_manifest(
    path: str,
    project_id: str | None = None,
    media_asset_id: str | None = None,
    horizons_media_asset_id: str | None = None,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    full_path, job_key = _resolve_stream_target(
        path=path,
        share_id=None,
        share_token=None,
        project_id=project_id,
        media_asset_id=media_asset_id or horizons_media_asset_id,
        vueio_session=vueio_session,
        db=db,
    )

    query = urlencode({'path': path, **({'project_id': project_id} if project_id else {}), **({'media_asset_id': media_asset_id or horizons_media_asset_id} if media_asset_id or horizons_media_asset_id else {})})
    return serve_hls_manifest(media_target(full_path, job_key), db, build_asset_url=HlsRouteBuilder('/api/hls/asset', query))


@router.get('/api/hls/asset/{asset_path:path}')
def hls_asset(
    asset_path: str,
    path: str,
    hls_generation: str | None = None,
    project_id: str | None = None,
    media_asset_id: str | None = None,
    horizons_media_asset_id: str | None = None,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    _full_path, job_key = _resolve_stream_target(
        path=path,
        share_id=None,
        share_token=None,
        project_id=project_id,
        media_asset_id=media_asset_id or horizons_media_asset_id,
        vueio_session=vueio_session,
        db=db,
    )

    query = urlencode({'path': path, **({'project_id': project_id} if project_id else {}), **({'media_asset_id': media_asset_id or horizons_media_asset_id} if media_asset_id or horizons_media_asset_id else {})})
    return serve_hls_asset(
        media_target(_full_path, job_key),
        asset_path=asset_path,
        build_asset_url=HlsRouteBuilder('/api/hls/asset', query),
        hls_generation=hls_generation,
    )
