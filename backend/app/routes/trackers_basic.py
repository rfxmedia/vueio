from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
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
    refresh_horizon_tracker_stats_cache,
    serialize_horizon_tracker_detail,
    serialize_horizon_tracker_summary,
    update_horizon_tracker,
)
from app.services.media import get_safe_path
from app.services.horizons.projects import require_horizon_project_writable
from app.services.project_delivery import build_delivery_logo_response, preserve_delivery_logo_upload, store_delivery_logo_source, store_delivery_logo_upload
from app.services.tracker_events import (
    build_tracker_event_actor,
    create_tracker_event,
    list_global_tracker_activity,
    list_tracker_activity,
    serialize_tracker_event,
    tracker_activity_visible_shot_ids,
)
from app.services.tracker_history import lock_tracker_for_history, preview_tracker_point_restore, restore_tracker_to_point
from app.services.tracker_views import TrackerViewRequest, list_tracker_views, record_tracker_view

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


class TrackerHistoryRestoreRequest(BaseModel):
    expected_state_hash: str = Field(min_length=64, max_length=64, pattern=r'^[0-9a-f]{64}$')


def _require_tracker_management(
    db: Session,
    *,
    project_id: str,
    user: dict,
    auth_mode: str,
    required_role: str,
) -> str:
    _project, access_role = require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role=required_role,
    )
    if is_restricted_horizon_artist(user, access_role):
        raise HTTPException(status_code=403, detail='Project content management access required')
    return access_role


def _record_tracker_update(
    db: Session,
    *,
    tracker,
    user: dict,
    auth_mode: str | None,
    fields: list[str],
) -> None:
    if not fields:
        return
    actor = build_tracker_event_actor(
        user=user,
        source='agent' if auth_mode == 'agent_key' else 'app',
    )
    create_tracker_event(
        db,
        project_id=tracker.project_id,
        tracker_id=tracker.id,
        event_type='tracker_updated',
        actor_id=actor['actor_id'],
        actor_name=actor['actor_name'] or 'Unknown',
        source=actor['source'] or 'app',
        payload={'fields': fields},
    )
    db.commit()


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
    access_role = _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = create_horizon_tracker(db, project_id=project_id, name=data.name)
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role=access_role)


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/duplicate')
def duplicate_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    access_role = _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = duplicate_horizon_tracker(db, project_id, tracker_ref)
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role=access_role, include_archived=True)


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
    before_id: int | None = None,
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
        before_id=before_id,
        visible_shot_ids=tracker_activity_visible_shot_ids(
            db,
            project_id=project_id,
            tracker_id=tracker.id,
            user=user,
            access_role=access_role,
        ),
        audience='restricted' if is_restricted_horizon_artist(user, access_role) else 'internal',
    )


def _require_tracker_restore_access(
    db: Session,
    *,
    project_id: str,
    tracker_ref: str,
    vueio_session: str | None,
    x_vueio_agent_key: str | None,
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role='owner',
    )
    if is_restricted_horizon_artist(user, access_role):
        raise HTTPException(status_code=403, detail='Project content management access required')
    require_horizon_project_writable(db, project_id)
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    if not tracker_tool_enabled_for_context(tracker, 'details', user=user, access_role=access_role):
        raise HTTPException(status_code=403, detail='Details are disabled for this tracker')
    return user, auth_mode, tracker


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/activity/{event_id}/restore-preview')
def get_tracker_activity_restore_preview(
    project_id: str,
    tracker_ref: str,
    event_id: int,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    _user, _auth_mode, tracker = _require_tracker_restore_access(
        db,
        project_id=project_id,
        tracker_ref=tracker_ref,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
    )
    lock_tracker_for_history(db, project_id=project_id, tracker_id=tracker.id)
    _user, _auth_mode, tracker = _require_tracker_restore_access(
        db,
        project_id=project_id,
        tracker_ref=tracker.id,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
    )
    return preview_tracker_point_restore(
        db,
        project_id=project_id,
        tracker_id=tracker.id,
        event_id=event_id,
    )


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/activity/{event_id}/restore')
def restore_tracker_activity(
    project_id: str,
    tracker_ref: str,
    event_id: int,
    data: TrackerHistoryRestoreRequest,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode, tracker = _require_tracker_restore_access(
        db,
        project_id=project_id,
        tracker_ref=tracker_ref,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
    )
    lock_tracker_for_history(db, project_id=project_id, tracker_id=tracker.id)
    user, auth_mode, tracker = _require_tracker_restore_access(
        db,
        project_id=project_id,
        tracker_ref=tracker.id,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
    )
    actor = build_tracker_event_actor(
        user=user,
        source='agent' if auth_mode == 'agent_key' else 'app',
    )
    try:
        restored_event, diff = restore_tracker_to_point(
            db,
            project_id=project_id,
            tracker_id=tracker.id,
            event_id=event_id,
            expected_state_hash=data.expected_state_hash,
            actor_id=actor['actor_id'],
            actor_name=actor['actor_name'] or 'Unknown',
            source=actor['source'] or 'app',
        )
        refresh_horizon_tracker_stats_cache(db, tracker, commit=False)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail='The tracker could not be restored safely. Nothing was changed.',
        )
    return {
        'status': 'restored',
        'message': 'Tracker restored. Your previous version is still available in History.',
        'event': serialize_tracker_event(restored_event, restoreable=True, current_point=True),
        **diff,
    }


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/views')
def record_authenticated_tracker_view(
    project_id: str,
    tracker_ref: str,
    data: TrackerViewRequest,
    request: Request,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role='viewer',
    )
    tracker = require_horizon_tracker_view_access(
        db,
        project_id,
        tracker_ref,
        user=user,
        access_role=access_role,
    )
    return record_tracker_view(
        db,
        request=request,
        project_id=project_id,
        tracker_id=tracker.id,
        data=data,
        user=user,
        access_role=access_role,
    )


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/views')
def get_tracker_views(
    project_id: str,
    tracker_ref: str,
    limit: int = 50,
    before: float | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role='admin',
    )
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    return list_tracker_views(
        db,
        project_id=project_id,
        tracker_id=tracker.id,
        limit=limit,
        before=before,
    )


@router.get('/api/tracker-activity/global')
def get_global_tracker_activity(
    limit: int = 40,
    before: float | None = None,
    before_id: int | None = None,
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
        before_id=before_id,
    )


@router.put('/api/projects/{project_id}/trackers/{tracker_ref}')
def update_tracker(project_id: str, tracker_ref: str, updates: TrackerUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    incoming_fields = set(updates.model_fields_set)
    if not incoming_fields:
        raise HTTPException(status_code=400, detail='No tracker changes provided')
    access_role = _require_tracker_management(
        db,
        project_id=project_id,
        user=user,
        auth_mode=auth_mode,
        required_role='owner' if incoming_fields & {'name', 'settings'} else 'editor',
    )
    tracker_fields = incoming_fields & {'name', 'settings'}
    tag_updates = None
    if 'tags' in incoming_fields:
        tag_updates = updates.tags
        tracker_fields.add('tags')
    elif 'categories' in incoming_fields:
        tag_updates = updates.categories
        tracker_fields.add('tags')
    current = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    before = {
        'name': current.name,
        'settings': current.settings_json,
        'tags': current.tags_json,
    }
    tracker = update_horizon_tracker(
        db,
        project_id,
        tracker_ref,
        name=updates.name,
        tags=tag_updates,
        settings=updates.settings,
        fields_set=tracker_fields,
        commit=False,
    )
    changed = [
        field for field, value in (
            ('name', tracker.name),
            ('settings', tracker.settings_json),
            ('tags', tracker.tags_json),
        )
        if field in tracker_fields and before[field] != value
    ]
    _record_tracker_update(
        db,
        tracker=tracker,
        user=user,
        auth_mode=auth_mode,
        fields=changed,
    )
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role=access_role)


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo')
def get_tracker_delivery_logo(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    return build_delivery_logo_response(tracker_settings_for(tracker)['delivery']['logo_upload_name'])


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo')
async def upload_tracker_delivery_logo(project_id: str, tracker_ref: str, file: UploadFile = File(...), vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    settings = tracker_settings_for(tracker)
    previous_logo = settings['delivery']['logo_upload_name']
    upload_name = await store_delivery_logo_upload(f'{project_id}-{tracker.id}', file)
    settings['delivery']['logo_upload_name'] = upload_name
    tracker = update_horizon_tracker(db, project_id, tracker_ref, settings=settings, fields_set={'settings'}, commit=False)
    _record_tracker_update(db, tracker=tracker, user=user, auth_mode=auth_mode, fields=['delivery logo'])
    if previous_logo and previous_logo != upload_name:
        preserve_delivery_logo_upload(previous_logo)
    return {'status': 'success', 'logo_upload_name': upload_name, 'settings': tracker_settings_for(tracker)}


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo/select')
def select_tracker_delivery_logo(project_id: str, tracker_ref: str, data: DeliveryLogoSourceRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    settings = tracker_settings_for(tracker)
    previous_logo = settings['delivery']['logo_upload_name']
    upload_name = store_delivery_logo_source(f'{project_id}-{tracker.id}', get_safe_path(data.source_path))
    settings['delivery']['logo_upload_name'] = upload_name
    tracker = update_horizon_tracker(db, project_id, tracker_ref, settings=settings, fields_set={'settings'}, commit=False)
    _record_tracker_update(db, tracker=tracker, user=user, auth_mode=auth_mode, fields=['delivery logo'])
    if previous_logo and previous_logo != upload_name:
        preserve_delivery_logo_upload(previous_logo)
    return {'status': 'success', 'logo_upload_name': upload_name, 'settings': tracker_settings_for(tracker)}


@router.delete('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo')
def remove_tracker_delivery_logo(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    settings = tracker_settings_for(tracker)
    previous_logo = settings['delivery']['logo_upload_name']
    settings['delivery']['logo_upload_name'] = ''
    tracker = update_horizon_tracker(db, project_id, tracker_ref, settings=settings, fields_set={'settings'}, commit=False)
    _record_tracker_update(db, tracker=tracker, user=user, auth_mode=auth_mode, fields=['delivery logo'])
    preserve_delivery_logo_upload(previous_logo)
    return {'status': 'success', 'logo_upload_name': '', 'settings': tracker_settings_for(tracker)}


@router.delete('/api/projects/{project_id}/trackers/{tracker_ref}')
def delete_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    delete_horizon_tracker(db, project_id, tracker_ref)
    return {'success': True}
