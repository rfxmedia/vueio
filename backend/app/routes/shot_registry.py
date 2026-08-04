from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HorizonProject
from app.services.auth import get_user_from_session
from app.services.project_access import check_project_permission, require_project_admin
from app.services.shot_registry import backfill_tracker_shot_registry, list_shot_registry_entries

router = APIRouter(tags=['shot-registry'])


def _require_legacy_shot_registry_project(db: Session, project_id: str) -> None:
    if db.query(HorizonProject).filter(HorizonProject.id == project_id).first():
        raise HTTPException(status_code=409, detail='Shot registry write-through backfill is legacy-only for now')


@router.get('/api/projects/{project_id}/shot-registry')
def get_project_shot_registry(project_id: str, tracker_name: str | None = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    if db.query(HorizonProject).filter(HorizonProject.id == project_id).first():
        raise HTTPException(status_code=409, detail='Horizons projects must use dedicated /api/horizons routes')
    user = get_user_from_session(vueio_session)
    if not check_project_permission(user, project_id):
        raise HTTPException(status_code=403, detail='Access denied to this project')
    entries = list_shot_registry_entries(db, project_id, tracker_name=tracker_name)
    return {'entries': [{
        'id': entry.id,
        'project_id': entry.project_id,
        'tracker_id': entry.tracker_id,
        'tracker_name': entry.tracker_name,
        'shot_id': entry.shot_id,
        'status': entry.status,
        'description': entry.description,
        'category': entry.category,
        'tag': entry.category,
        'latest_version_number': entry.latest_version_number,
        'latest_file_path': entry.latest_file_path,
        'latest_media_asset_id': entry.latest_media_asset_id,
        'source': entry.source,
        'created_at': entry.created_at,
        'updated_at': entry.updated_at,
    } for entry in entries]}


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shot-registry/backfill')
def backfill_project_shot_registry(project_id: str, tracker_name: str, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    _require_legacy_shot_registry_project(db, project_id)
    require_project_admin(project_id, vueio_session)
    return backfill_tracker_shot_registry(db, project_id, tracker_name)
