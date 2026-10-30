"""Extras of tracker shots: add, fill, replace, rename, reorder, remove, download."""
from __future__ import annotations

import json
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HorizonShot, HorizonShotExtra, HorizonShotExtraFile, HorizonShotVersion, MediaAsset, UploadItem
from app.routes.horizons_fresh import _auth_ctx, _commit_horizons_shot_result, _horizons_shot_context
from app.routes.share_media import _validate_shared_horizons_object_share
from app.services.auth import get_request_agent_identity
from app.services.horizons.extras import (
    EXTRA_NAME_MAX_LENGTH,
    EXTRA_NOTE_MAX_LENGTH,
    load_version_extra_entries,
    numbered_extra_names,
    shot_extras_by_shot,
)
from app.services.horizons.projects import require_horizon_project_writable
from app.services.horizons_fresh import (
    get_horizon_tracker_by_ref,
    is_restricted_horizon_artist,
    require_horizon_project_access,
    require_horizon_shot_view_access,
)
from app.services.media_serving import DownloadAuditSpec, media_target, serve_download
from app.services.project_content_gateway import resolve_horizons_object_auth, resolve_horizons_object_share
from app.services.shot_extras import ShotExtrasService
from app.services.trackers import queue_thumbnail_warmup_for_paths
from app.services.upload_links import UPLOAD_LINK_CHUNK_SIZE, issue_upload_link_token, request_origin, upload_link_command
from app.services.uploads import create_project_upload_session

router = APIRouter(tags=['shot-extras'])


class ExtraCreate(BaseModel):
    name: str = Field(max_length=EXTRA_NAME_MAX_LENGTH, description='Such as Alpha matte, Holdout matte, Clean plate, Element or Reference.')
    note: str | None = Field(None, max_length=EXTRA_NOTE_MAX_LENGTH, description='A short description, such as Window.')
    client_visible: bool = Field(True, description='False keeps the extra for your team only. Clients never see it.')
    version_id: str | None = Field(None, description='The version that gets the file. Leave out for the latest version.')
    file_path: str | None = Field(None, description='A file in the project. Leave out file_path and media_asset_id to ask for the extra: it shows as needed until a version gets a file.')
    media_asset_id: str | None = None


class ExtraUpdate(BaseModel):
    name: str | None = Field(None, max_length=EXTRA_NAME_MAX_LENGTH)
    note: str | None = Field(None, max_length=EXTRA_NOTE_MAX_LENGTH, description='Empty removes the note.')
    client_visible: bool | None = None


class ExtraOrder(BaseModel):
    extra_ids: list[str] = Field(description='Every extra id of the shot once, in the new order.')


class ExtraFileSet(BaseModel):
    file_path: str | None = Field(None, description='A file in the project.')
    media_asset_id: str | None = None
    from_version_id: str | None = Field(None, description='Use the file this extra has on another version, such as the previous one.')


class ExtraUpload(BaseModel):
    filename: str = Field(max_length=255)
    size: int = Field(ge=0)
    extra_id: str | None = Field(None, description='The extra that gets the file. Leave out to add a new extra with name, note and client_visible.')
    name: str | None = Field(None, max_length=EXTRA_NAME_MAX_LENGTH)
    note: str | None = Field(None, max_length=EXTRA_NOTE_MAX_LENGTH)
    client_visible: bool = True


def _command(db: Session, project_id: str, shot_id: str, vueio_session: str | None, x_vueio_agent_key: str | None):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    tracker = get_horizon_tracker_by_ref(db, project_id, shot.tracker_id)
    return ctx, access_role, shot, _horizons_shot_context(project_id, tracker, ctx, access_role)


def _commit(db: Session, result, project_id: str) -> None:
    _commit_horizons_shot_result(db, result, project_id)
    # Extras show their thumbnail on the card at once, as versions do.
    if result.queued_media_paths:
        queue_thumbnail_warmup_for_paths(result.queued_media_paths, db=db, project_id=project_id, storage_scope='tracker_version')


def _actor_id(ctx) -> str | None:
    return ctx.user.get('id') or ctx.user.get('username')


def _extra_payload(db: Session, shot: HorizonShot, extra_id: str) -> dict:
    extras = shot_extras_by_shot(db, [shot.id])[shot.id]
    names = numbered_extra_names(extras)
    extra = next((item for item in extras if item.id == extra_id), None)
    if extra is None:
        return {}
    files = db.query(HorizonShotExtraFile).filter(HorizonShotExtraFile.extra_id == extra.id).all()
    return {
        'id': extra.id, 'shot_id': shot.id, 'name': names[extra.id], 'base_name': extra.name, 'note': extra.note,
        'client_visible': bool(extra.client_visible), 'sort_order': extra.sort_order,
        'files': [{'version_id': file.version_id, 'media_asset_id': file.media_asset_id} for file in files],
    }


@router.post('/api/horizons/projects/{project_id}/shots/{shot_id}/extras', summary='Add an extra to a shot', openapi_extra={'x-mcp-tool': 'extra_add'})
def add_shot_extra(project_id: str, shot_id: str, data: ExtraCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Add an extra, such as an alpha matte, to a shot.

    With file_path or media_asset_id, the version (the latest unless
    version_id is set) gets that file. Without a file, the extra is asked
    for: it shows as needed on every version until one gets a file. A new
    version starts with every extra needed. To upload a file from your
    computer, use extra_upload. Members with review access can only add an
    extra with a file.
    """
    ctx, _role, shot, command_ctx = _command(db, project_id, shot_id, vueio_session, x_vueio_agent_key)
    result, extra = ShotExtrasService(db).add_extra(
        command_ctx, shot, name=data.name, note=data.note, client_visible=data.client_visible,
        version_id=data.version_id, file_path=data.file_path, media_asset_id=data.media_asset_id, created_by=_actor_id(ctx),
    )
    _commit(db, result, project_id)
    return _extra_payload(db, shot, extra.id)


@router.patch('/api/horizons/projects/{project_id}/shots/{shot_id}/extras/{extra_id}', summary='Change an extra')
def update_shot_extra(project_id: str, shot_id: str, extra_id: str, data: ExtraUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Rename an extra, change its note, or change whether clients see it.

    Send only the fields to change. The change applies to every version.
    """
    _ctx, _role, shot, command_ctx = _command(db, project_id, shot_id, vueio_session, x_vueio_agent_key)
    result, extra = ShotExtrasService(db).update_extra(
        command_ctx, shot, extra_id, fields=set(data.model_fields_set),
        name=data.name, note=data.note, client_visible=data.client_visible,
    )
    _commit(db, result, project_id)
    return _extra_payload(db, shot, extra.id)


@router.put('/api/horizons/projects/{project_id}/shots/{shot_id}/extras/order', summary='Reorder the extras of a shot')
def reorder_shot_extras(project_id: str, shot_id: str, data: ExtraOrder, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Set the order of the extras. Extras with the same name are numbered in this order."""
    _ctx, _role, shot, command_ctx = _command(db, project_id, shot_id, vueio_session, x_vueio_agent_key)
    result = ShotExtrasService(db).reorder_extras(command_ctx, shot, data.extra_ids)
    _commit(db, result, project_id)
    return {'extra_ids': [extra.id for extra in shot_extras_by_shot(db, [shot.id])[shot.id]]}


@router.delete('/api/horizons/projects/{project_id}/shots/{shot_id}/extras/{extra_id}', summary='Remove an extra from a shot')
def remove_shot_extra(project_id: str, shot_id: str, extra_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Remove an extra from the shot and from every version. The files stay in the project."""
    _ctx, _role, shot, command_ctx = _command(db, project_id, shot_id, vueio_session, x_vueio_agent_key)
    result = ShotExtrasService(db).remove_extra(command_ctx, shot, extra_id)
    _commit(db, result, project_id)
    return {'status': 'removed', 'extra_id': extra_id}


@router.put('/api/horizons/projects/{project_id}/shots/{shot_id}/extras/{extra_id}/versions/{version_id}', summary='Give an extra a file', openapi_extra={'x-mcp-tool': 'extra_file_set'})
def set_shot_extra_file(project_id: str, shot_id: str, extra_id: str, version_id: str, data: ExtraFileSet, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Give an extra its file for one version, or replace it.

    Send one of: file_path (a project file), media_asset_id, or
    from_version_id to use the file this extra has on another version. Other
    versions keep their own files.
    """
    ctx, _role, shot, command_ctx = _command(db, project_id, shot_id, vueio_session, x_vueio_agent_key)
    result, _row = ShotExtrasService(db).set_file(
        command_ctx, shot, extra_id, version_id, file_path=data.file_path, media_asset_id=data.media_asset_id,
        from_version_id=data.from_version_id, created_by=_actor_id(ctx),
    )
    _commit(db, result, project_id)
    return _extra_payload(db, shot, extra_id)


@router.delete('/api/horizons/projects/{project_id}/shots/{shot_id}/extras/{extra_id}/versions/{version_id}', summary='Remove the file of an extra from a version')
def clear_shot_extra_file(project_id: str, shot_id: str, extra_id: str, version_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """The extra stays on the shot and shows as needed on this version. The file stays in the project."""
    _ctx, _role, shot, command_ctx = _command(db, project_id, shot_id, vueio_session, x_vueio_agent_key)
    result = ShotExtrasService(db).clear_file(command_ctx, shot, extra_id, version_id)
    _commit(db, result, project_id)
    return _extra_payload(db, shot, extra_id)


def _upload_folder(db: Session, version: HorizonShotVersion, restricted: bool) -> str:
    """Put an extra next to its plate when the plate is a project file."""
    asset = db.get(MediaAsset, version.media_asset_id) if version.media_asset_id else None
    if asset is None or asset.storage_scope != 'project' or restricted:
        return ''
    folder = str(PurePosixPath(asset.file_path).parent)
    return '' if folder in ('.', '') else folder


@router.post('/api/horizons/projects/{project_id}/shots/{shot_id}/versions/{version_id}/extras/upload', summary='Upload an extra', openapi_extra={'x-mcp-tool': 'extra_upload'})
def upload_shot_extra(project_id: str, shot_id: str, version_id: str, data: ExtraUpload, request: Request, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Upload a file from your computer as an extra of one version.

    With extra_id, the file goes to that extra. Without it, a new extra is
    added with name, note and client_visible. This call does not send the
    file. It returns an upload link, used as with version_upload: send the
    file in parts of `chunk_size` bytes to `upload_url` with `upload_token`
    in X-Vueio-Upload-Token, or run `command`. After the last part, Vue.io
    gives the extra its file. The file goes next to the version's file in the
    project; for members with review access, into their workspace.
    """
    ctx, access_role, shot, _command_ctx = _command(db, project_id, shot_id, vueio_session, x_vueio_agent_key)
    require_horizon_project_writable(db, project_id)
    version = db.query(HorizonShotVersion).filter(HorizonShotVersion.id == version_id, HorizonShotVersion.shot_id == shot.id).first()
    if version is None:
        raise HTTPException(status_code=404, detail='Version not found')
    if data.extra_id:
        if db.query(HorizonShotExtra.id).filter(HorizonShotExtra.id == data.extra_id, HorizonShotExtra.shot_id == shot.id).first() is None:
            raise HTTPException(status_code=404, detail='Extra not found')
    elif not (data.name or '').strip():
        raise HTTPException(status_code=400, detail='Give the extra a name, such as Alpha matte')
    filename = PurePosixPath(data.filename.replace('\\', '/')).name.strip()
    if not filename:
        raise HTTPException(status_code=400, detail='The file needs a name')
    restricted = is_restricted_horizon_artist(ctx.user, access_role)
    session, items = create_project_upload_session(
        db,
        project_id=project_id,
        user=ctx.user,
        access_role=access_role,
        target_path=_upload_folder(db, version, restricted),
        uploader_name=ctx.user.get('display_name') or ctx.user.get('username') or 'Project uploader',
        client_batch_id=f'extra-upload:{uuid.uuid4().hex}',
        manifest=[{'rel_path': filename, 'original_name': filename, 'size_bytes': data.size}],
    )
    agent = get_request_agent_identity()
    item = items[0]
    item.version_upload_json = json.dumps({
        'kind': 'extra', 'user_id': ctx.user['id'], 'agent_key_id': agent['key_id'] if agent else None,
        'project_id': project_id, 'shot_id': shot.id, 'version_id': version.id, 'extra_id': data.extra_id,
        'name': data.name, 'note': data.note, 'client_visible': data.client_visible,
    })
    db.commit()
    token, expires_at = issue_upload_link_token(item_id=item.id)
    upload_url = f'/api/upload-links/{item.id}'
    return {
        'upload_url': upload_url,
        'upload_token': token,
        'chunk_size': UPLOAD_LINK_CHUNK_SIZE,
        'expires_at': expires_at,
        'command': upload_link_command(f'{request_origin(request)}{upload_url}', token, data.size),
    }


def finish_extra_upload(db: Session, link: dict, ctx, item: UploadItem) -> None:
    """Give the extra its uploaded file. The receipt and the change commit together."""
    _project, access_role = require_horizon_project_access(db, link['project_id'], ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, link['project_id'], link['shot_id'], user=ctx.user, access_role=access_role)
    tracker = get_horizon_tracker_by_ref(db, link['project_id'], shot.tracker_id)
    command_ctx = _horizons_shot_context(link['project_id'], tracker, ctx, access_role)
    service = ShotExtrasService(db)
    created_by = ctx.user.get('id') or ctx.user.get('username')
    if link.get('extra_id'):
        result, row = service.set_file(command_ctx, shot, link['extra_id'], link['version_id'], file_path=item.final_path, created_by=created_by)
        extra_id = row.extra_id
    else:
        result, extra = service.add_extra(
            command_ctx, shot, name=link.get('name') or '', note=link.get('note'), client_visible=bool(link.get('client_visible', True)),
            version_id=link['version_id'], file_path=item.final_path, created_by=created_by,
        )
        extra_id = extra.id
    item.version_upload_json = json.dumps({**link, 'extra_id': extra_id, 'completed': True})
    _commit(db, result, link['project_id'])


def _download_extra(db: Session, request: Request, *, shot: HorizonShot, version: HorizonShotVersion, extra_id: str,
                    share=None, user=None, access_role=None):
    entry = next((item for item in load_version_extra_entries(db, shot, version, share=share is not None) if item.extra.id == extra_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail='This version has no file for this extra')
    resolved = (
        resolve_horizons_object_share(share, db, asset_id=entry.file.media_asset_id)
        if share is not None
        else resolve_horizons_object_auth(db, version.project_id, asset_id=entry.file.media_asset_id, detail='Extra not found', user=user, access_role=access_role)
    )
    full_path = resolved.full_path
    audit = {
        'project_id': version.project_id,
        'tracker_id': version.tracker_id,
        'event_type': 'download_file',
        'resource_type': 'shot_extra',
        'resource_id': entry.file.id,
        'resource_name': entry.name,
        'filename': entry.download_name,
        'paths': [resolved.canonical_path or ''],
        'size_bytes': full_path.stat().st_size if full_path and full_path.is_file() else None,
    }
    audit.update({'source': 'share', 'share_id': share.id, 'metadata': {'share_type': share.share_type}} if share is not None else {'source': 'app', 'user': user})
    return serve_download(
        media_target(full_path, resolved.cache_identity),
        db,
        request=request,
        audit=DownloadAuditSpec(audit),
        not_found_detail='The file of this extra is offline',
        audit_before_exists=True,
        filename=entry.download_name,
    )


@router.get('/api/horizons/projects/{project_id}/shot-versions/{version_id}/extras/{extra_id}/download')
def download_shot_extra(project_id: str, version_id: str, extra_id: str, request: Request, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    # The version resolver applies the same access rules as the plate.
    resolve_horizons_object_auth(db, project_id, version_id=version_id, detail='Horizons shot version not found', user=ctx.user, access_role=access_role)
    version = db.get(HorizonShotVersion, version_id)
    shot = db.get(HorizonShot, version.shot_id)
    return _download_extra(db, request, shot=shot, version=version, extra_id=extra_id, user=ctx.user, access_role=access_role)


@router.get('/api/projects/shared/{share_id}/shot-versions/{version_id}/extras/{extra_id}/download')
def download_shared_shot_extra(share_id: str, version_id: str, extra_id: str, request: Request, share_token: str | None = None, db: Session = Depends(get_db)):
    share = _validate_shared_horizons_object_share(share_id, share_token, db)
    if not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    # Published, and in the shared tracker or page.
    resolve_horizons_object_share(share, db, version_id=version_id)
    version = db.get(HorizonShotVersion, version_id)
    shot = db.get(HorizonShot, version.shot_id)
    return _download_extra(db, request, shot=shot, version=version, extra_id=extra_id, share=share)
