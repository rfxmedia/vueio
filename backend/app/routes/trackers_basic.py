from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth import get_request_user
from app.services.horizons_fresh import (
    compute_horizon_tracker_stats,
    create_horizon_tracker,
    delete_horizon_tracker,
    duplicate_horizon_tracker,
    get_horizon_tracker_by_ref,
    is_restricted_horizon_artist,
    list_horizon_trackers,
    tracker_settings_for,
    tracker_tool_enabled_for_context,
    require_horizon_project_access,
    require_horizon_tracker_view_access,
    serialize_horizon_tracker_detail,
    serialize_horizon_tracker_summary,
    update_horizon_tracker,
)
from app.services.media import get_safe_path
from app.services.project_delivery import build_delivery_logo_response, delete_delivery_logo_upload, store_delivery_logo_source, store_delivery_logo_upload
from app.services.tracker_events import list_global_tracker_activity, list_tracker_activity, tracker_activity_visible_shot_ids

router = APIRouter(tags=['trackers-basic'])


class TrackerCreate(BaseModel):
    name: str


class TrackerUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: Optional[str] = None
    categories: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    settings: Optional[dict] = None


class DeliveryLogoSourceRequest(BaseModel):
    source_path: str


@router.get('/api/projects/{project_id}/trackers')
def list_trackers(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    trackers = [serialize_horizon_tracker_summary(db, tracker, user=user, access_role=access_role) for tracker in list_horizon_trackers(db, project_id)]
    if is_restricted_horizon_artist(user, access_role):
        trackers = [tracker for tracker in trackers if (tracker.get('shot_count') or 0) > 0]
    return {'trackers': trackers}


@router.post('/api/projects/{project_id}/trackers')
def create_tracker(project_id: str, data: TrackerCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='admin')
    tracker = create_horizon_tracker(db, project_id=project_id, name=data.name)
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role='admin')


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/duplicate')
def duplicate_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='admin')
    tracker = duplicate_horizon_tracker(db, project_id, tracker_ref)
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role='admin', include_archived=True)


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}')
def get_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    include_archived = (
        not is_restricted_horizon_artist(user, access_role) and
        (access_role or '') in {'admin', 'owner', 'editor'}
    )
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role=access_role, include_archived=include_archived)


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/stats')
def get_tracker_stats(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    if not tracker_tool_enabled_for_context(tracker, 'details', user=user, access_role=access_role):
        raise HTTPException(status_code=403, detail='Details are disabled for this tracker')
    return compute_horizon_tracker_stats(db, tracker, user=user, access_role=access_role)


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/activity')
def get_tracker_activity(
    project_id: str,
    tracker_ref: str,
    limit: int = 40,
    before: float | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    if not tracker_tool_enabled_for_context(tracker, 'details', user=user, access_role=access_role):
        raise HTTPException(status_code=403, detail='Details are disabled for this tracker')
    return list_tracker_activity(
        db,
        project_id=project_id,
        tracker_id=tracker.id,
        limit=limit,
        before=before,
        visible_shot_ids=tracker_activity_visible_shot_ids(
            db,
            project_id=project_id,
            tracker_id=tracker.id,
            user=user,
            access_role=access_role,
        ),
    )


@router.get('/api/tracker-activity/global')
def get_global_tracker_activity(
    limit: int = 40,
    before: float | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    return list_global_tracker_activity(
        db,
        user=user,
        auth_mode=auth_mode,
        limit=limit,
        before=before,
    )


@router.put('/api/projects/{project_id}/trackers/{tracker_ref}')
def update_tracker(project_id: str, tracker_ref: str, updates: TrackerUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    incoming_fields = set(updates.model_fields_set)
    if not incoming_fields:
        raise HTTPException(status_code=400, detail='No tracker changes provided')
    require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role='admin' if incoming_fields & {'name', 'settings'} else 'editor',
    )
    tracker_fields = incoming_fields & {'name', 'settings'}
    tag_updates = None
    if 'tags' in incoming_fields:
        tag_updates = updates.tags
        tracker_fields.add('tags')
    elif 'categories' in incoming_fields:
        tag_updates = updates.categories
        tracker_fields.add('tags')
    tracker = update_horizon_tracker(
        db,
        project_id,
        tracker_ref,
        name=updates.name,
        tags=tag_updates,
        settings=updates.settings,
        fields_set=tracker_fields,
    )
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role='admin')


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo')
def get_tracker_delivery_logo(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    return build_delivery_logo_response(tracker_settings_for(tracker)['delivery']['logo_upload_name'])


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo')
async def upload_tracker_delivery_logo(project_id: str, tracker_ref: str, file: UploadFile = File(...), vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='admin')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    settings = tracker_settings_for(tracker)
    previous_logo = settings['delivery']['logo_upload_name']
    upload_name = await store_delivery_logo_upload(f'{project_id}-{tracker.id}', file)
    settings['delivery']['logo_upload_name'] = upload_name
    tracker = update_horizon_tracker(db, project_id, tracker_ref, settings=settings, fields_set={'settings'})
    if previous_logo and previous_logo != upload_name:
        delete_delivery_logo_upload(previous_logo)
    return {'status': 'success', 'logo_upload_name': upload_name, 'settings': tracker_settings_for(tracker)}


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo/select')
def select_tracker_delivery_logo(project_id: str, tracker_ref: str, data: DeliveryLogoSourceRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='admin')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    settings = tracker_settings_for(tracker)
    previous_logo = settings['delivery']['logo_upload_name']
    upload_name = store_delivery_logo_source(f'{project_id}-{tracker.id}', get_safe_path(data.source_path))
    settings['delivery']['logo_upload_name'] = upload_name
    tracker = update_horizon_tracker(db, project_id, tracker_ref, settings=settings, fields_set={'settings'})
    if previous_logo and previous_logo != upload_name:
        delete_delivery_logo_upload(previous_logo)
    return {'status': 'success', 'logo_upload_name': upload_name, 'settings': tracker_settings_for(tracker)}


@router.delete('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo')
def remove_tracker_delivery_logo(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='admin')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    settings = tracker_settings_for(tracker)
    previous_logo = settings['delivery']['logo_upload_name']
    settings['delivery']['logo_upload_name'] = ''
    tracker = update_horizon_tracker(db, project_id, tracker_ref, settings=settings, fields_set={'settings'})
    delete_delivery_logo_upload(previous_logo)
    return {'status': 'success', 'logo_upload_name': '', 'settings': tracker_settings_for(tracker)}


@router.delete('/api/projects/{project_id}/trackers/{tracker_ref}')
def delete_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='admin')
    delete_horizon_tracker(db, project_id, tracker_ref)
    return {'success': True}
