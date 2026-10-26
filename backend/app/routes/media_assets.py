from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.file_access import require_file_browser_read_access
from app.services.media_assets import backfill_tracker_media_asset_ids, list_media_assets, normalize_storage_scope, register_media_asset, serialize_media_asset
from app.services.media_resolution import resolve_project_content_target
from app.services.project_access import require_project_admin, require_project_auth

router = APIRouter(tags=['media-assets'])


class MediaAssetRegisterRequest(BaseModel):
    file_path: str = Field(description='Relative to the project folder. For storage_scope media_root, a path in shared storage.')
    storage_scope: str = Field('project', description='project or media_root.')


@router.get('/api/projects/{project_id}/media-assets', deprecated=True, summary='List legacy project media assets')
def get_project_media_assets(project_id: str, scope: str | None = None, kind: str | None = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """List all media asset records of a project, also unavailable ones.

    Only administrators can use it. For current projects, use
    get_horizons_media_assets. `scope` and `kind` filter as in that route.
    """
    require_project_auth(project_id, vueio_session)
    assets = list_media_assets(db, project_id, scope=scope, kind=kind)
    return {'assets': [serialize_media_asset(asset) for asset in assets]}


@router.post('/api/projects/{project_id}/media-assets/register', deprecated=True, summary='Register a media asset')
def register_project_media_asset(project_id: str, data: MediaAssetRegisterRequest, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Record a file as a media asset of a project and return the record.

    Only administrators can use it. For current projects, use
    post_horizons_project_file_register.
    """
    require_project_auth(project_id, vueio_session)
    storage_scope = normalize_storage_scope(data.storage_scope)
    file_path = str(data.file_path or '').strip().strip('/')
    if storage_scope == 'media_root':
        linked_path, _cache_key, linked_scope = resolve_project_content_target(project_id, file_path)
        if linked_path and linked_scope == 'media_root':
            file_path = linked_path.resolve().relative_to(get_settings().MEDIA_ROOT.resolve()).as_posix()
        else:
            require_file_browser_read_access(vueio_session, file_path)
    elif storage_scope != 'project':
        raise HTTPException(status_code=400, detail='Unsupported media storage scope')

    asset = register_media_asset(db, project_id, file_path, storage_scope=storage_scope)
    if not asset:
        raise HTTPException(status_code=404, detail='Media file not found')
    return serialize_media_asset(asset)


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/media-assets/backfill', deprecated=True, summary='Backfill legacy tracker media ids')
def backfill_tracker_media_assets(project_id: str, tracker_name: str, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Add media asset ids to the versions of an old file-based tracker.

    `tracker_name` is the name of a .tracker.json file in the project folder.
    Current trackers are in the database, so they return 404. Administrators
    only.
    """
    require_project_admin(project_id, vueio_session)
    return backfill_tracker_media_asset_ids(db, project_id, tracker_name)
