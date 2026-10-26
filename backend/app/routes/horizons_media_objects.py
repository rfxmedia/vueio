from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth import get_request_user
from app.services.horizons_fresh import require_horizon_project_access
from app.services.media_serving import (
    DownloadAuditSpec,
    HlsRouteBuilder,
    get_object_file_info,
    get_object_hls_asset,
    get_object_hls_manifest,
    get_object_hls_status,
    get_object_scrub_sprite,
    get_object_thumbnail,
    media_target,
    require_thumbnail_target,
    save_object_thumbnail,
    serve_download,
    set_object_thumbnail,
    stream_object_file,
)
from app.services.project_content_gateway import object_payload_tuple, resolve_horizons_object_auth
from app.services.horizons.common import ROLE_RANK
from app.services.model_preview import save_model_thumbnail, serve_model
from app.services.comment_visuals import frame_timestamp, render_media_frame
from app.services.comparison import comparison_file, comparison_status, resolve_comparison
from app.services.comparison_export import EXPORT_OPENAPI, cancel_export, read_export_request, resolve_export, start_export
from app.services.tracker_downloads import tracker_version_download_name

router = APIRouter(tags=['horizons-media-objects'])


def _authorized_comparison(project_id, version_id, other_id, vueio_session, x_vueio_agent_key, db):
    user, role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    sources = [resolve_horizons_object_auth(db, project_id, version_id=identity,
               detail='Shot version not found', user=user, access_role=role) for identity in (version_id, other_id)]
    return resolve_comparison(db, *sources, user=user, access_role=role), f'user:{user.get("id") or user["username"]}'


@router.api_route('/api/horizons/projects/{project_id}/shot-versions/{version_id}/comparison/{other_id}/status', methods=['GET', 'POST'], summary='Prepare a version comparison')
def horizons_comparison_status(project_id: str, version_id: str, other_id: str, request: Request, response: Response,
                              vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Start or check a two-up video of two versions of the same shot.

    `version_id` and `other_id` are shot version ids of two videos. The
    tracker's comparison tool must be on. Call again until `status` is
    complete, then get the video with horizons_comparison_file. The POST form
    retries after an error.
    """
    pair, _owner = _authorized_comparison(project_id, version_id, other_id, vueio_session, x_vueio_agent_key, db)
    response.headers['Cache-Control'] = 'private, no-store'
    return comparison_status(db, pair, retry=request.method == 'POST')


@router.api_route('/api/horizons/projects/{project_id}/shot-versions/{version_id}/comparison/{other_id}/file', methods=['GET', 'HEAD'])
def horizons_comparison_file(project_id: str, version_id: str, other_id: str,
                            vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    pair, _owner = _authorized_comparison(project_id, version_id, other_id, vueio_session, x_vueio_agent_key, db)
    return comparison_file(pair)


@router.post('/api/horizons/projects/{project_id}/shot-versions/{version_id}/comparison/{other_id}/export', summary='Export a version comparison', openapi_extra=EXPORT_OPENAPI)
async def horizons_comparison_export(project_id: str, version_id: str, other_id: str, request: Request, response: Response,
                               vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Start rendering a comparison clip of two shot versions as an MP4 file.

    Send JSON {"options": {...}}. Options: `end_frame` (required),
    `start_frame`, `mode` (wipe or side-by-side), `aspect` (source, 3:4, 1:1
    or 16:9), `swapped`, `freeze_frame`, `freeze_frames`, `wipe_start` and
    `wipe_duration` (0 to 1). Frames count at the comparison frame rate. The
    clip is 5 minutes or less. Keep the returned `token`; it lasts 24 hours.
    """
    # The same resolvers used by individual downloads check access to BOTH versions.
    pair, owner = await run_in_threadpool(_authorized_comparison, project_id, version_id, other_id, vueio_session, x_vueio_agent_key, db)
    response.headers['Cache-Control'] = 'private, no-store'
    data = await read_export_request(request)
    return await run_in_threadpool(start_export, db, pair, owner, data)


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/comparison/{other_id}/export/{token}', summary='Get comparison export status')
@router.delete('/api/horizons/projects/{project_id}/shot-versions/{version_id}/comparison/{other_id}/export/{token}', summary='Cancel a comparison export')
def horizons_comparison_export_status(project_id: str, version_id: str, other_id: str, token: str, request: Request, response: Response,
                                      vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Check or cancel one comparison export.

    `token` comes from horizons_comparison_export. When `status` is complete,
    download the MP4 with horizons_comparison_export_file. The delete form
    cancels the export; a complete export is not removed.
    """
    pair, owner = _authorized_comparison(project_id, version_id, other_id, vueio_session, x_vueio_agent_key, db)
    exported = resolve_export(pair, owner, token)
    response.headers['Cache-Control'] = 'private, no-store'
    return cancel_export(exported) if request.method == 'DELETE' else comparison_status(db, exported, start=False)


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/comparison/{other_id}/export/{token}/file')
@router.head('/api/horizons/projects/{project_id}/shot-versions/{version_id}/comparison/{other_id}/export/{token}/file')
def horizons_comparison_export_file(project_id: str, version_id: str, other_id: str, token: str,
                                    vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    pair, owner = _authorized_comparison(project_id, version_id, other_id, vueio_session, x_vueio_agent_key, db)
    return comparison_file(resolve_export(pair, owner, token), filename='comparison.mp4')


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


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/file-info', summary='Get media file details')
def get_horizons_media_asset_file_info(project_id: str, asset_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get the details of a project media file.

    Returns its name, path, size, dates and kind. A video also has duration,
    fps, frame count, resolution and codec.
    """
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
def hls_status_horizons_media_asset(project_id: str, asset_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db), retry: bool = False):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_status(lambda: _build_horizons_object_payload(
        db,
        project_id,
        asset_id=asset_id,
        detail='Horizons media asset not found',
        user=user,
        access_role=access_role,
    ), db, retry=retry)


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
@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/thumbnail', summary='Get a media file thumbnail')
def thumbnail_horizons_media_asset(project_id: str, asset_id: str, cached_only: bool = False, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return a thumbnail image of a project media file.

    For an image file, returns the image itself. When a video has no thumbnail
    yet, one is made in the background and a placeholder is returned. With
    `cached_only` true, no new thumbnail is made.
    """
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


@router.post('/api/horizons/projects/{project_id}/media-assets/{asset_id}/thumbnail', summary='Set a media file thumbnail')
async def set_horizons_media_asset_thumbnail(project_id: str, asset_id: str, file: UploadFile = File(...), vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Replace the thumbnail of a project media file with an uploaded image.

    The image can be up to 20 MB. It is resized and saved as a JPEG. The media
    file does not change. Image files keep showing the image itself.
    """
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


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/file-info', summary='Get shot version file details')
def get_horizons_shot_version_file_info(project_id: str, version_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get the details of the media file of a shot version.

    Returns its name, path, size, dates and kind. A video also has duration,
    fps, frame count, resolution and codec.
    """
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
def hls_status_horizons_shot_version(project_id: str, version_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db), retry: bool = False):
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_hls_status(lambda: _build_horizons_object_payload(
        db,
        project_id,
        version_id=version_id,
        detail='Horizons shot version not found',
        user=user,
        access_role=access_role,
    ), db, retry=retry)


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


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/scrub', summary='Get a version scrub sheet')
def scrub_horizons_shot_version(project_id: str, version_id: str, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return one JPEG with 30 small frames of a video version, for scrubbing.

    The frames are evenly spaced, in 6 columns and 5 rows of 320 by 180
    pixels. While the sheet is being made, the response is 202; try again
    after 2 seconds. Videos only.
    """
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    return get_object_scrub_sprite(
        lambda: _build_horizons_object_payload(
            db,
            project_id,
            version_id=version_id,
            detail='Horizons shot version not found',
            user=user,
            access_role=access_role,
        ),
        db,
    )


@router.head('/api/horizons/projects/{project_id}/shot-versions/{version_id}/thumbnail')
@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/thumbnail', summary='Get a shot version thumbnail')
def thumbnail_horizons_shot_version(project_id: str, version_id: str, cached_only: bool = False, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return a thumbnail image of a shot version.

    For an image file, returns the image itself. When a video has no thumbnail
    yet, one is made in the background and a placeholder is returned. With
    `cached_only` true, no new thumbnail is made.
    """
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


def _frame_image(full_path, time: float | None, frame: int | None) -> bytes:
    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail='Media file not found')
    if time is not None and frame is not None:
        raise HTTPException(status_code=400, detail='Give time or frame, not both')
    return render_media_frame(full_path, frame_timestamp(full_path, frame) if frame is not None else time or 0)


def _frame_response(full_path, time: float | None, frame: int | None) -> Response:
    return Response(_frame_image(full_path, time, frame), media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})


_FRAME_TIME = Query(None, ge=0, description='Seconds from the start of the video. The default is 0. Ignored for images.')
_FRAME_NUMBER = Query(None, ge=0, description='Frame number from 0, instead of time. Ignored for images.')


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/frame', summary='Get a frame of a shot version', openapi_extra={'x-mcp-tool': 'frame_get'})
def frame_horizons_shot_version(project_id: str, version_id: str, time: float | None = _FRAME_TIME, frame: int | None = _FRAME_NUMBER, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return one frame of a shot version as a JPEG image, 960 pixels wide.

    Use it to see the work under review. Give `time` in seconds or `frame`.
    For an image version, returns the image.
    """
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    full_path, _cache_key, _payload = _build_horizons_object_payload(
        db,
        project_id,
        version_id=version_id,
        detail='Horizons shot version not found',
        user=user,
        access_role=access_role,
    )
    db.close()
    return _frame_response(full_path, time, frame)


@router.get('/api/horizons/projects/{project_id}/media-assets/{asset_id}/frame', summary='Get a frame of a media file')
def frame_horizons_media_asset(project_id: str, asset_id: str, time: float | None = _FRAME_TIME, frame: int | None = _FRAME_NUMBER, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return one frame of a project media file as a JPEG image, 960 pixels wide.

    Give `time` in seconds or `frame`.
    """
    user, access_role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    full_path, _cache_key, _payload = _build_horizons_object_payload(
        db,
        project_id,
        asset_id=asset_id,
        detail='Horizons media asset not found',
        user=user,
        access_role=access_role,
    )
    db.close()
    return _frame_response(full_path, time, frame)


@router.post('/api/horizons/projects/{project_id}/shot-versions/{version_id}/thumbnail', summary='Set a shot version thumbnail')
async def set_horizons_shot_version_thumbnail(project_id: str, version_id: str, file: UploadFile = File(...), vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Replace the thumbnail of a shot version with an uploaded image.

    The image can be up to 20 MB. It is resized and saved as a JPEG. The media
    file does not change. Image versions keep showing the image itself.
    """
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


class ThumbnailFrame(BaseModel):
    time: Optional[float] = Field(None, ge=0, description='Seconds from the start of the video.')
    frame: Optional[int] = Field(None, ge=0, description='Frame number from 0, instead of time.')

    @model_validator(mode='after')
    def _one_moment(self):
        if self.time is None and self.frame is None:
            raise ValueError('Give time or frame.')
        if self.time is not None and self.frame is not None:
            raise ValueError('Give time or frame, not both.')
        return self


@router.post('/api/horizons/projects/{project_id}/shot-versions/{version_id}/thumbnail/frame', summary='Set a shot version thumbnail from a frame')
def set_horizons_shot_version_thumbnail_from_frame(project_id: str, version_id: str, data: ThumbnailFrame, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Use one frame of a video version as its thumbnail.

    Give `time` in seconds or `frame`. Check the frame first with frame_get.
    The media file does not change. Image versions keep showing the image
    itself.
    """
    user, access_role = _require_horizons_media_editor(project_id, vueio_session, x_vueio_agent_key, db)
    full_path, cache_key, _payload = _build_horizons_object_payload(
        db,
        project_id,
        version_id=version_id,
        detail='Horizons shot version not found',
        user=user,
        access_role=access_role,
    )
    db.close()
    require_thumbnail_target(full_path, cache_key, not_found_detail='Horizons shot version file not found')
    return save_object_thumbnail(cache_key, _frame_image(full_path, data.time, data.frame))


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
    download_name = tracker_version_download_name(db, version_id, full_path)
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
            'filename': download_name or (full_path.name if full_path else None),
            'paths': [payload.get('path') or ''],
            'size_bytes': full_path.stat().st_size if full_path and full_path.is_file() else None,
            'metadata': {'access_role': access_role},
        }),
        not_found_detail='Horizons shot version file not found',
        audit_before_exists=True,
        # Clients get the tracker's name and version, such as glow shot_V8.mov.
        filename=download_name,
    )


@router.api_route('/api/horizons/projects/{project_id}/media-assets/{asset_id}/model', methods=['GET', 'POST'])
@router.api_route('/api/horizons/projects/{project_id}/shot-versions/{version_id}/model', methods=['GET', 'POST'])
def model_horizons_object(project_id: str, request: Request, asset_id: str | None = None, version_id: str | None = None,
                          resource: str = 'manifest', name: str = '', frame: int = 0, generation: str = '',
                          vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, role = _require_horizons_media_viewer(project_id, vueio_session, x_vueio_agent_key, db)
    target = resolve_horizons_object_auth(db, project_id, asset_id=asset_id, version_id=version_id,
                                         detail='Model not found', user=user, access_role=role)
    return serve_model(target.full_path, target.cache_identity, db, resource=resource, name=name, frame=frame,
                       generation=generation, retry=request.method == 'POST', publisher=ROLE_RANK.get(role, 0) >= ROLE_RANK['editor'])


# Editors may set custom thumbnails, so they may also store rendered ones.
@router.put('/api/horizons/projects/{project_id}/media-assets/{asset_id}/model')
@router.put('/api/horizons/projects/{project_id}/shot-versions/{version_id}/model')
async def put_horizons_model_thumbnail(project_id: str, generation: str, asset_id: str | None = None, version_id: str | None = None,
                                       file: UploadFile = File(...), vueio_session: str | None = Cookie(None),
                                       x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    def resolve():
        user, role = _require_horizons_media_editor(project_id, vueio_session, x_vueio_agent_key, db)
        return resolve_horizons_object_auth(db, project_id, asset_id=asset_id, version_id=version_id,
                                            detail='Model not found', user=user, access_role=role)
    target = await run_in_threadpool(resolve)
    return await save_model_thumbnail(target.full_path, file, generation)
