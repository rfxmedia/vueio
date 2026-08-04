from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import HorizonShot, MediaAsset, ShareLink
from app.services.agent_keys import (
    create_agent_key,
    delete_agent_key,
    list_agent_keys,
    reissue_agent_key,
    revoke_agent_key,
    serialize_agent_key,
    update_agent_key,
)
from app.services.auth import get_request_user, load_users, require_admin
from app.services.download_audit import list_download_events
from app.services.horizons_fresh import get_horizon_project
from app.services.media import VIDEO_EXTENSIONS, get_safe_path
from app.services.media_pipeline import trigger_auto_hls_package
from app.services.release_updates import get_update_status
from app.services.app_identity import (
    build_team_logo_response,
    clear_team_logo,
    get_app_identity_record,
    save_app_identity,
    serialize_app_identity,
    set_team_logo,
    store_team_logo_source,
    store_team_logo_upload,
)
from app.services.share_management import apply_share_management_update, serialize_share_for_management
from app.services.streaming import clear_transcode_cache
from app.services.trackers import queue_thumbnail_warmup_for_paths
from app.services.theme import get_app_theme_record, reset_app_theme, save_app_theme, serialize_app_theme

router = APIRouter(tags=['admin'])
settings = get_settings()


class ShareUpdate(BaseModel):
    expires_at: Optional[float] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    allow_download: Optional[bool] = None
    allow_upload: Optional[bool] = None


class AgentKeyCreate(BaseModel):
    name: Optional[str] = None
    user_id: Optional[str] = None


class AgentKeyUpdate(BaseModel):
    name: Optional[str] = None
    user_id: Optional[str] = None
    is_active: Optional[bool] = None


class ThemeUpdate(BaseModel):
    colors: dict[str, str]


class AppIdentityUpdate(BaseModel):
    team_name: Optional[str] = None
    website_url: Optional[str] = None


class IdentityLogoSourceRequest(BaseModel):
    source_path: str


def _require_admin_session(vueio_session: str | None) -> dict:
    return require_admin(vueio_session)


@router.get('/api/identity')
def get_identity(db: Session = Depends(get_db)):
    return serialize_app_identity(get_app_identity_record(db))


@router.get('/api/identity/logo')
def get_identity_logo(db: Session = Depends(get_db)):
    record = get_app_identity_record(db)
    return build_team_logo_response(record.logo_upload_name)


@router.get('/api/theme')
def get_theme(db: Session = Depends(get_db)):
    return serialize_app_theme(get_app_theme_record(db))


@router.put('/api/admin/identity')
def update_identity(data: AppIdentityUpdate, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_admin_session(vueio_session)
    record = save_app_identity(
        db,
        team_name=data.team_name,
        website_url=data.website_url,
        updated_by=user.get('id') or user.get('username'),
    )
    return serialize_app_identity(record)


@router.post('/api/admin/identity/logo')
async def upload_identity_logo(file: UploadFile = File(...), vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_admin_session(vueio_session)
    upload_name = await store_team_logo_upload(file)
    record = set_team_logo(db, upload_name, updated_by=user.get('id') or user.get('username'))
    return serialize_app_identity(record)


@router.post('/api/admin/identity/logo/select')
def select_identity_logo(data: IdentityLogoSourceRequest, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_admin_session(vueio_session)
    upload_name = store_team_logo_source(get_safe_path(data.source_path))
    record = set_team_logo(db, upload_name, updated_by=user.get('id') or user.get('username'))
    return serialize_app_identity(record)


@router.delete('/api/admin/identity/logo')
def delete_identity_logo(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_admin_session(vueio_session)
    record = clear_team_logo(db, updated_by=user.get('id') or user.get('username'))
    return serialize_app_identity(record)


@router.get('/api/admin/shares')
def list_all_shares(
    limit: int = 100,
    offset: int = 0,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    _require_admin_session(vueio_session)

    total = db.query(ShareLink).count()
    shares = db.query(ShareLink).order_by(ShareLink.created_at.desc()).offset(offset).limit(limit).all()
    project_cache = {}

    result = [serialize_share_for_management(share, db, project_cache) for share in shares]
    return {'shares': result, 'total': total, 'limit': limit, 'offset': offset}


@router.get('/api/admin/download-events')
def get_admin_download_events(
    limit: int = 100,
    project_id: str | None = None,
    share_id: str | None = None,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    _require_admin_session(vueio_session)
    return list_download_events(db, limit=limit, project_id=project_id, share_id=share_id)


@router.put('/api/admin/shares/{share_id}')
def update_share(share_id: str, data: ShareUpdate, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)

    share = db.query(ShareLink).filter(ShareLink.id == share_id).first()
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
    return {'status': 'updated'}


@router.delete('/api/admin/shares/{share_id}')
def delete_share(share_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)

    share = db.query(ShareLink).filter(ShareLink.id == share_id).first()
    if not share:
        raise HTTPException(status_code=404, detail='Share not found')

    db.delete(share)
    db.commit()
    return {'status': 'deleted'}


@router.get('/api/admin/agent-keys')
def get_admin_agent_keys(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    users = load_users()
    return {
        'keys': [
            {
                **serialize_agent_key(record),
                'user_display_name': (users.get(record.user_id) or {}).get('display_name') or record.user_id,
            }
            for record in list_agent_keys(db)
        ],
    }


@router.post('/api/admin/agent-keys')
def post_admin_agent_key(data: AgentKeyCreate, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_admin_session(vueio_session)
    users = load_users()
    if data.user_id is not None and data.user_id not in users:
        raise HTTPException(status_code=400, detail='Agent key user not found')
    record, token = create_agent_key(db, name=data.name, user_id=data.user_id, created_by=user['id'])
    return {
        'key': {
            **serialize_agent_key(record),
            'user_display_name': (users.get(record.user_id) or {}).get('display_name') or record.user_id,
        },
        'token': token,
    }


@router.put('/api/admin/agent-keys/{key_id}')
def put_admin_agent_key(key_id: str, data: AgentKeyUpdate, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    users = load_users()
    if data.user_id is not None and data.user_id not in users:
        raise HTTPException(status_code=400, detail='Agent key user not found')
    record = update_agent_key(db, key_id, name=data.name, user_id=data.user_id, is_active=data.is_active)
    return {
        'key': {
            **serialize_agent_key(record),
            'user_display_name': (users.get(record.user_id) or {}).get('display_name') or record.user_id,
        }
    }


@router.post('/api/admin/agent-keys/{key_id}/reissue')
def post_admin_agent_key_reissue(key_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    users = load_users()
    record, token = reissue_agent_key(db, key_id)
    return {
        'key': {
            **serialize_agent_key(record),
            'user_display_name': (users.get(record.user_id) or {}).get('display_name') or record.user_id,
        },
        'token': token,
    }


@router.post('/api/admin/agent-keys/{key_id}/revoke')
def post_admin_agent_key_revoke(key_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    users = load_users()
    record = revoke_agent_key(db, key_id)
    return {
        'key': {
            **serialize_agent_key(record),
            'user_display_name': (users.get(record.user_id) or {}).get('display_name') or record.user_id,
        }
    }


@router.delete('/api/admin/agent-keys/{key_id}')
def delete_admin_agent_key(key_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    delete_agent_key(db, key_id)
    return {'status': 'deleted', 'id': key_id}


@router.get('/api/admin/system-health')
def system_health(vueio_session: str | None = Cookie(None)):
    _require_admin_session(vueio_session)

    import os
    import shutil

    result = {}
    try:
        with open('/proc/uptime') as handle:
            uptime_secs = float(handle.read().split()[0])
            result['uptime_seconds'] = int(uptime_secs)
            days = int(uptime_secs // 86400)
            hours = int((uptime_secs % 86400) // 3600)
            result['uptime_human'] = f'{days}d {hours}h' if days else f'{hours}h'
    except Exception:
        result['uptime_human'] = '—'

    try:
        with open('/proc/loadavg') as handle:
            parts = handle.read().split()
            result['load_1m'] = float(parts[0])
            result['load_5m'] = float(parts[1])
            result['load_15m'] = float(parts[2])
        result['cpu_count'] = os.cpu_count() or 1
        result['cpu_percent'] = round(result['load_1m'] / result['cpu_count'] * 100, 1)
    except Exception:
        result['cpu_percent'] = 0
        result['cpu_count'] = 1

    try:
        meminfo = {}
        with open('/proc/meminfo') as handle:
            for line in handle:
                if ':' in line:
                    key, value = line.split(':', 1)
                    meminfo[key.strip()] = int(value.strip().split()[0])
        total = meminfo.get('MemTotal', 0)
        available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
        used = total - available
        result['mem_total_gb'] = round(total / 1024 / 1024, 1)
        result['mem_used_gb'] = round(used / 1024 / 1024, 1)
        result['mem_percent'] = round(used / total * 100, 1) if total else 0
    except Exception:
        result['mem_total_gb'] = 0
        result['mem_used_gb'] = 0
        result['mem_percent'] = 0

    try:
        disk = shutil.disk_usage('/app/data')
        result['disk_total_gb'] = round(disk.total / 1024**3, 1)
        result['disk_used_gb'] = round(disk.used / 1024**3, 1)
        result['disk_free_gb'] = round(disk.free / 1024**3, 1)
        result['disk_percent'] = round(disk.used / disk.total * 100, 1) if disk.total else 0
    except Exception:
        result['disk_total_gb'] = 0
        result['disk_used_gb'] = 0
        result['disk_free_gb'] = 0
        result['disk_percent'] = 0

    result['engine_status'] = 'running'
    try:
        db_path = settings.database_dir / 'vueio.db'
        if db_path.exists():
            result['db_size_mb'] = round(db_path.stat().st_size / 1024 / 1024, 1)
    except Exception:
        pass

    return result


@router.get('/api/admin/update-status')
def update_status(refresh: bool = False, vueio_session: str | None = Cookie(None)):
    _require_admin_session(vueio_session)
    return get_update_status(force_refresh=refresh)


@router.delete('/api/admin/transcodes')
def reset_transcodes(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    return clear_transcode_cache(db)


@router.post('/api/admin/projects/{project_id}/media-warmup')
def warm_project_review_media(project_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    get_horizon_project(db, project_id)

    asset_ids = sorted({
        asset_id
        for asset_id, in (
            db.query(HorizonShot.latest_media_asset_id)
            .filter(HorizonShot.project_id == project_id)
            .filter(HorizonShot.latest_media_asset_id.isnot(None))
            .all()
        )
        if asset_id
    })
    if not asset_ids:
        return {'status': 'queued', 'assets': 0, 'hls': 0, 'thumbnails': 0}

    assets = db.query(MediaAsset).filter(MediaAsset.id.in_(asset_ids)).all()
    hls_count = 0
    thumbnail_count = 0
    for asset in assets:
        if Path(asset.file_path).suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        trigger_auto_hls_package(asset.file_path, db, project_id=project_id, storage_scope=asset.storage_scope)
        hls_count += 1
        thumbnail_count += queue_thumbnail_warmup_for_paths(
            [asset.file_path],
            db=db,
            project_id=project_id,
            storage_scope=asset.storage_scope,
        )

    return {'status': 'queued', 'assets': len(assets), 'hls': hls_count, 'thumbnails': thumbnail_count}


@router.put('/api/admin/theme')
def put_admin_theme(data: ThemeUpdate, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_admin_session(vueio_session)
    record = save_app_theme(db, data.colors, updated_by=user['id'])
    return serialize_app_theme(record)


@router.delete('/api/admin/theme')
def delete_admin_theme(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_admin_session(vueio_session)
    record = reset_app_theme(db, updated_by=user['id'])
    return serialize_app_theme(record)
