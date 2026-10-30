from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, File, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Comment, HorizonShot, HorizonShotVersion, MediaAsset
from app.services.auth import get_request_user
from app.services.horizons.shots import visible_horizon_shots_query
from app.services.horizons.team import _horizon_shot_assignment_clause, serialize_horizon_shot_assignments
from app.services.horizons.trackers import _serialize_horizon_tracker_tags, serialize_horizon_shot_version_media
from app.services.media_resolution import resolve_media_asset_path
from app.services.file_access import require_user_file_browser_read_access
from app.services.horizons.common import SHOT_STATUS_ORDER
from app.services.horizons.extras import summarize_version_extras
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
    description: Optional[str] = None


class TrackerUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: Optional[str] = None
    description: Optional[str] = None
    categories: Optional[list[str]] = Field(None, description='Old name for tags. Ignored when tags is given.')
    tags: Optional[list[str]] = Field(None, description='The tracker tag list, in display order. It replaces the current list.')
    settings: Optional[dict] = Field(None, description='Settings to change, in the shape returned in `settings`. Settings left out keep their values.')


class DeliveryLogoSourceRequest(BaseModel):
    source_path: str = Field(description='An image file path, relative to the media root.')


class TrackerHistoryRestoreRequest(BaseModel):
    expected_state_hash: str = Field(min_length=64, max_length=64, pattern=r'^[0-9a-f]{64}$', description='The expected_state_hash from get_tracker_activity_restore_preview.')


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


@router.get('/api/projects/{project_id}/trackers', summary='List trackers', openapi_extra={'x-mcp-tool': 'trackers_list'})
def list_trackers(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List a project's trackers with their ids, names, descriptions and shot counts."""
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    trackers = [serialize_horizon_tracker_summary(db, tracker, user=user, access_role=access_role) for tracker in list_horizon_trackers(db, project_id)]
    if is_restricted_horizon_artist(user, access_role):
        trackers = [tracker for tracker in trackers if (tracker.get('shot_count') or 0) > 0]
    return {'trackers': trackers}


@router.post('/api/projects/{project_id}/trackers', summary='Create a tracker')
def create_tracker(project_id: str, data: TrackerCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create an empty tracker in a project.

    The name must be unique in the project, in any case. The description is
    cut to 240 characters. Returns the new tracker.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    access_role = _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = create_horizon_tracker(db, project_id=project_id, name=data.name, description=data.description)
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role=access_role)


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/duplicate', summary='Duplicate a tracker')
def duplicate_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Copy a tracker with its shots, assignees and versions.

    `tracker_ref` is the tracker id, slug or name. The copy is named
    "<name> Copy", with a number if needed. It uses the same media files.
    Comments, activity and the delivery logo are not copied.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    access_role = _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = duplicate_horizon_tracker(db, project_id, tracker_ref)
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role=access_role, include_archived=True)


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}', summary='Get a tracker with every shot and version')
def get_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get one tracker with its settings, tags, shots and every version.

    `tracker_ref` is the tracker id, slug or name. Archived shots have an
    `archived_at` time; viewers do not get them. For a compact list of many
    shots, use tracker_overview.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    include_archived = (
        not is_restricted_horizon_artist(user, access_role) and
        (access_role or '') in {'admin', 'owner', 'editor'}
    )
    return serialize_horizon_tracker_detail(db, tracker, user=user, access_role=access_role, include_archived=include_archived)


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/overview', summary='Tracker overview', openapi_extra={'x-mcp-tool': 'tracker_overview'})
def get_tracker_overview(
    project_id: str,
    tracker_ref: str,
    status: Optional[str] = Query(None, description=f"Only shots with this status: {', '.join(SHOT_STATUS_ORDER)}."),
    tag: Optional[str] = Query(None, description='Only shots with this tag.'),
    assignee: Optional[str] = Query(None, description='Only shots assigned to this user id.'),
    q: Optional[str] = Query(None, description='Only shots whose code or description contains this text.'),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """One tracker in compact form, for reading many shots at once.

    Each shot has its code, status, tag, description, assignees, version count
    and latest version with its open comment threads. A latest version lists
    its extras, such as mattes: `needed` is true while an extra has no file on
    that version. Archived shots are left out. Use a latest version's `id`
    with frame_get, comments_list or comment_post, and an extra's `id` with
    extra_file_set or extra_upload. get_tracker returns every field and every
    version.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    query = visible_horizon_shots_query(db, project_id, tracker_id=tracker.id, user=user, access_role=access_role)
    tags = _serialize_horizon_tracker_tags(tracker, query.with_entities(HorizonShot.category).distinct().all(),
                                          restrict_to_visible_shots=is_restricted_horizon_artist(user, access_role))
    text = (q or '').strip().lower()
    if status:
        query = query.filter(HorizonShot.status == status)
    if tag:
        query = query.filter(HorizonShot.category == tag)
    if assignee:
        query = query.filter(_horizon_shot_assignment_clause({assignee}))
    if text:
        query = query.filter(or_(func.lower(HorizonShot.shot_code).contains(text, autoescape=True),
                                 func.lower(HorizonShot.description).contains(text, autoescape=True)))
    total = query.count()
    page = query.order_by(HorizonShot.created_at, HorizonShot.id).offset(offset).limit(limit).all()
    assignments = serialize_horizon_shot_assignments(db, page)
    ranked = db.query(
        HorizonShotVersion.id.label('version_id'),
        func.count().over(partition_by=HorizonShotVersion.shot_id).label('version_count'),
        func.row_number().over(partition_by=HorizonShotVersion.shot_id, order_by=(
            case((HorizonShotVersion.label == HorizonShot.latest_version_label, 0), else_=1),
            HorizonShotVersion.created_at.desc(), HorizonShotVersion.id.desc(),
        )).label('rank'),
    ).join(HorizonShot, HorizonShot.id == HorizonShotVersion.shot_id).filter(
        HorizonShotVersion.project_id == project_id, HorizonShotVersion.shot_id.in_([shot.id for shot in page]),
    ).subquery()
    versions = db.query(HorizonShotVersion, MediaAsset, ranked.c.version_count).join(
        ranked, ranked.c.version_id == HorizonShotVersion.id,
    ).outerjoin(MediaAsset, MediaAsset.id == HorizonShotVersion.media_asset_id).filter(ranked.c.rank == 1).all() if page else []
    latest = {}
    for version, asset, count in versions:
        if asset:
            resolve_media_asset_path(asset, project_id=project_id, db=db)
        latest[version.shot_id] = (serialize_horizon_shot_version_media(version, asset), count)
    counts = {
        version_id: (int(open_threads or 0), int(count))
        for version_id, open_threads, count in db.query(
            Comment.horizons_shot_version_id,
            func.sum(case((Comment.parent_comment_id.is_(None) & Comment.resolved.is_(False), 1), else_=0)),
            func.count(),
        ).filter(Comment.project_id == project_id, Comment.horizons_shot_version_id.in_([version.id for version, _, _ in versions]))
        .group_by(Comment.horizons_shot_version_id).all()
    } if versions else {}
    extras = summarize_version_extras(db, {version.id: version.shot_id for version, _, _ in versions})
    items = []
    for shot in page:
        version, version_count = latest.get(shot.id, (None, 0))
        item = {
            'id': shot.id,
            'code': shot.shot_code,
            'status': shot.status,
            'tag': shot.category,
            'description': shot.description or '',
            'assignees': [
                {'id': person.get('id'), 'name': person.get('display_name') or person.get('username')}
                for person in assignments[shot.id]['assignees']
            ],
            'version_count': version_count,
            'updated_at': shot.updated_at,
            'latest_version': None,
        }
        if version:
            open_threads, comment_count = counts.get(version['id'], (0, 0))
            item['latest_version'] = {
                'id': version['id'],
                'label': version.get('label'),
                'file_path': version.get('file_path'),
                'kind': 'video' if version.get('is_video') else 'image' if version.get('is_image') else 'pdf' if version.get('is_pdf') else '3d' if version.get('is_model') else 'file',
                'published': version.get('share_state') == 'published',
                'created_at': version.get('created_at'),
                'available': bool(version.get('exists', True)) and not version.get('unavailable_at'),
                'open_comment_threads': open_threads,
                'comment_count': comment_count,
            }
            if version['id'] in extras:
                item['latest_version']['extras'] = extras[version['id']]
        items.append(item)
    return {
        'tracker': {
            'id': tracker.id,
            'name': tracker.name,
            'description': tracker.description or '',
            'statuses': SHOT_STATUS_ORDER,
            'tags': tags,
        },
        'total': total,
        'offset': offset,
        'next_offset': offset + limit if offset + limit < total else None,
        'shots': items,
    }


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/stats', summary='Get tracker statistics')
def get_tracker_stats(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get shot, version, status and duration totals for a tracker.

    `tracker_ref` is the tracker id, slug or name. Durations and frames come
    from the latest version of each shot. The tracker's details tool must be
    on for you.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    if not tracker_tool_enabled_for_context(tracker, 'details', user=user, access_role=access_role):
        raise HTTPException(status_code=403, detail='Details are disabled for this tracker')
    return compute_horizon_tracker_stats(db, tracker, user=user, access_role=access_role)


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/activity', summary='List tracker activity')
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
    """List the history events of a tracker, newest first.

    `tracker_ref` is the tracker id, slug or name. `limit` is 1 to 100. For the
    next page, send `next_before` and `next_before_id` from the result as
    `before` and `before_id`. An event with `restoreable` true is a history
    point that restore_tracker_activity can return the tracker to.
    """
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


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/activity/{event_id}/restore-preview', summary='Preview a tracker restore')
def get_tracker_activity_restore_preview(
    project_id: str,
    tracker_ref: str,
    event_id: int,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Show what changes if the tracker returns to its state after one event.

    `tracker_ref` is the tracker id, slug or name; `event_id` is an activity
    event id. Nothing changes. Send the returned `expected_state_hash` to
    restore_tracker_activity.
    """
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


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/activity/{event_id}/restore', summary='Restore a tracker to a history point')
def restore_tracker_activity(
    project_id: str,
    tracker_ref: str,
    event_id: int,
    data: TrackerHistoryRestoreRequest,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Return a tracker to its state after one activity event.

    `tracker_ref` is the tracker id, slug or name; `event_id` is an activity
    event id. Restores the tracker name and settings, shots, assignees,
    versions and comments. The current state is saved first, so you can undo
    it. A change after the preview makes the restore fail with 409.
    """
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


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/views', summary='List tracker views')
def get_tracker_views(
    project_id: str,
    tracker_ref: str,
    limit: int = 50,
    before: float | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """List who opened a tracker and which media they viewed, newest first.

    `tracker_ref` is the tracker id, slug or name. `active` lists people seen in
    the last two minutes. `limit` is 1 to 100; send `next_before` as `before`
    for the next page. Admins only.
    """
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


@router.get('/api/tracker-activity/global', summary='List activity in all projects')
def get_global_tracker_activity(
    limit: int = 40,
    before: float | None = None,
    before_id: int | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """List tracker events from every project you can see, newest first.

    Each event has its project and tracker names. `limit` is 1 to 100. For the
    next page, send `next_before` and `next_before_id` from the result as
    `before` and `before_id`.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    return list_global_tracker_activity(
        db,
        user=user,
        auth_mode=auth_mode,
        limit=limit,
        before=before,
        before_id=before_id,
    )


@router.put('/api/projects/{project_id}/trackers/{tracker_ref}', summary='Update a tracker')
def update_tracker(project_id: str, tracker_ref: str, updates: TrackerUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change a tracker's name, description, tags or settings.

    `tracker_ref` is the tracker id, slug or name. Send only the fields to
    change. Records a tracker_updated event that lists the changed fields.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    incoming_fields = set(updates.model_fields_set)
    if not incoming_fields:
        raise HTTPException(status_code=400, detail='No tracker changes provided')
    access_role = _require_tracker_management(
        db,
        project_id=project_id,
        user=user,
        auth_mode=auth_mode,
        required_role='owner' if incoming_fields & {'name', 'description', 'settings'} else 'editor',
    )
    tracker_fields = incoming_fields & {'name', 'description', 'settings'}
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
        'description': current.description,
        'settings': current.settings_json,
        'tags': current.tags_json,
    }
    settings = updates.settings
    if isinstance(settings, dict):
        # Settings left out keep their values, so a partial update resets nothing.
        merged = tracker_settings_for(current)
        for key, value in settings.items():
            base = merged.get(key)
            merged[key] = {**base, **value} if isinstance(base, dict) and isinstance(value, dict) else value
        settings = merged
    tracker = update_horizon_tracker(
        db,
        project_id,
        tracker_ref,
        name=updates.name,
        description=updates.description,
        tags=tag_updates,
        settings=settings,
        fields_set=tracker_fields,
        commit=False,
    )
    changed = [
        field for field, value in (
            ('name', tracker.name),
            ('description', tracker.description),
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


@router.get('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo', summary='Get the tracker delivery logo')
def get_tracker_delivery_logo(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return the delivery logo image of a tracker.

    `tracker_ref` is the tracker id, slug or name. Returns 404 when the tracker
    has no logo.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_ref, user=user, access_role=access_role)
    return build_delivery_logo_response(tracker_settings_for(tracker)['delivery']['logo_upload_name'])


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo', summary='Upload a tracker delivery logo')
async def upload_tracker_delivery_logo(project_id: str, tracker_ref: str, file: UploadFile = File(...), vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Upload an image as the tracker's delivery logo, replacing the old one.

    `tracker_ref` is the tracker id, slug or name. The image can be up to 2 MB.
    The logo appears in the tracker's delivery view. Records a tracker_updated
    event.
    """
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


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo/select', summary='Use a file as the delivery logo')
def select_tracker_delivery_logo(project_id: str, tracker_ref: str, data: DeliveryLogoSourceRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Copy an existing image file to be the tracker's delivery logo.

    `tracker_ref` is the tracker id, slug or name. The source file is copied;
    it does not change. Records a tracker_updated event.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    # Like project covers: only a file this person may open in the File Browser.
    require_user_file_browser_read_access(user, data.source_path)
    settings = tracker_settings_for(tracker)
    previous_logo = settings['delivery']['logo_upload_name']
    upload_name = store_delivery_logo_source(f'{project_id}-{tracker.id}', get_safe_path(data.source_path))
    settings['delivery']['logo_upload_name'] = upload_name
    tracker = update_horizon_tracker(db, project_id, tracker_ref, settings=settings, fields_set={'settings'}, commit=False)
    _record_tracker_update(db, tracker=tracker, user=user, auth_mode=auth_mode, fields=['delivery logo'])
    if previous_logo and previous_logo != upload_name:
        preserve_delivery_logo_upload(previous_logo)
    return {'status': 'success', 'logo_upload_name': upload_name, 'settings': tracker_settings_for(tracker)}


@router.delete('/api/projects/{project_id}/trackers/{tracker_ref}/delivery-logo', summary='Remove the delivery logo')
def remove_tracker_delivery_logo(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Remove the delivery logo from a tracker.

    `tracker_ref` is the tracker id, slug or name. The stored image is kept so
    tracker history can bring it back. Records a tracker_updated event.
    """
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


@router.delete('/api/projects/{project_id}/trackers/{tracker_ref}', summary='Delete a tracker')
def delete_tracker(project_id: str, tracker_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a tracker permanently, with everything in it.

    `tracker_ref` is the tracker id, slug or name. Also deletes its shots,
    versions, comments with their attachment files, activity, view and
    download records, share links and delivery logo. Version media files stay
    on disk. You cannot undo this.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _require_tracker_management(db, project_id=project_id, user=user, auth_mode=auth_mode, required_role='owner')
    delete_horizon_tracker(db, project_id, tracker_ref)
    return {'success': True}
