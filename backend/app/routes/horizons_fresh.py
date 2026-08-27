from __future__ import annotations

from fastapi import APIRouter, Body, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import HorizonShotAssignee
from app.services.auth import get_request_user, load_users
from app.services.horizons_fresh import (
    build_horizon_project_snapshot,
    create_horizon_project,
    create_horizon_project_folder,
    create_horizon_tracker,
    delete_horizon_project_file,
    delete_horizon_project_folder,
    ensure_horizon_project_membership_for_user,
    get_horizon_assignable_user,
    is_restricted_horizon_artist,
    remove_horizon_project_membership_for_user,
    get_horizon_tracker_by_ref,
    get_horizon_user_workspace_path,
    get_horizon_shot_assignee_ids,
    grant_horizon_project_access,
    list_horizon_project_grants,
    list_horizon_shot_versions,
    list_horizon_trackers,
    list_visible_horizon_media_assets,
    list_visible_horizon_projects,
    list_visible_horizon_shots,
    move_horizon_project_file,
    move_horizon_project_folder,
    register_horizon_project_file,
    rename_horizon_project_file,
    rename_horizon_project_folder,
    require_horizon_user_workspace_path,
    require_horizon_shot_view_access,
    revoke_horizon_project_access,
    require_horizon_project_access,
    require_horizon_tracker_view_access,
    refresh_horizon_tracker_stats_cache,
    tracker_settings_for,
    serialize_horizon_project,
    serialize_horizon_shot_assignee,
    serialize_horizon_shot_assignees,
    serialize_horizon_team_user,
    update_horizon_project,
    update_horizon_tracker,
)
from app.services.media_assets import declare_media_asset, serialize_media_asset
from app.services.shot_commands import ShotCommandActor, ShotCommandContext, ShotCommandService
from app.services.tracker_events import build_tracker_event_actor, create_tracker_event

router = APIRouter(tags=['horizons-fresh'])


def _horizons_shot_context(project_id: str, tracker, ctx, access_role: str) -> ShotCommandContext:
    actor_id = (ctx.user or {}).get('id') or (ctx.user or {}).get('username')
    actor_name = (ctx.user or {}).get('display_name') or (ctx.user or {}).get('username') or 'User'
    source = 'agent' if ctx.auth_mode == 'agent_key' else 'app'
    return ShotCommandContext(
        project_id=project_id,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        access_role=access_role,
        actor=ShotCommandActor(user=ctx.user, auth_mode=ctx.auth_mode, source=source, actor_id=actor_id, actor_name=actor_name),
        can_create_shot=True,
        can_update_shot=True,
        can_delete_shot=False,
        can_delete_versions=False,
        can_archive_shot=False,
        restricted_artist=is_restricted_horizon_artist(ctx.user),
        event_mode='full',
    )


def _commit_horizons_shot_result(db: Session, result, project_id: str) -> None:
    for tracker_id in result.stats_dirty_tracker_ids:
        refresh_horizon_tracker_stats_cache(db, get_horizon_tracker_by_ref(db, project_id, tracker_id), commit=False)
    db.commit()


class HorizonProjectCreate(BaseModel):
    title: str
    slug: str | None = None
    description: str | None = None
    status: str | None = 'active'
    visibility: str | None = 'private'


class HorizonProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None


class HorizonTrackerCreate(BaseModel):
    name: str
    slug: str | None = None


class HorizonTrackerUpdate(BaseModel):
    name: str | None = None
    settings: dict | None = None


class HorizonShotCreate(BaseModel):
    shot_code: str
    description: str | None = None
    status: str | None = 'not_started'
    category: str | None = None
    tag: str | None = None
    assignee_user_id: str | None = None
    assignee_user_ids: list[str] | None = None


class HorizonShotUpdate(BaseModel):
    description: str | None = None
    status: str | None = None
    category: str | None = None
    tag: str | None = None
    assignee_user_id: str | None = None
    assignee_user_ids: list[str] | None = None


class HorizonShotVersionCreate(BaseModel):
    label: str
    media_asset_id: str | None = None
    notes: str | None = None


class HorizonShotVersionUpdate(BaseModel):
    media_asset_id: str | None = None
    notes: str | None = None


class HorizonProjectGrantCreate(BaseModel):
    subject_type: str
    subject_id: str
    role: str = 'viewer'


class HorizonMediaAssetDeclare(BaseModel):
    file_path: str
    storage_scope: str = 'horizons_declared'
    content_hash: str | None = None
    file_size: int | None = None
    modified_at: float | None = None


class HorizonProjectFolderCreate(BaseModel):
    path: str


class HorizonProjectFileRegister(BaseModel):
    file_path: str


class HorizonProjectFileRename(BaseModel):
    path: str
    new_name: str


class HorizonProjectFolderRename(BaseModel):
    path: str
    new_name: str


class _AuthCtx(BaseModel):
    user: dict
    auth_mode: str


def _shot_tag_value(data) -> str | None:
    if 'tag' in getattr(data, 'model_fields_set', set()):
        return data.tag
    return getattr(data, 'category', None)


def _shot_update_fields(data) -> set[str]:
    fields = set(getattr(data, 'model_fields_set', set()))
    if 'tag' in fields:
        fields.add('category')
        fields.discard('tag')
    return fields


def _auth_ctx(vueio_session: str | None, x_vueio_agent_key: str | None) -> _AuthCtx:
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    return _AuthCtx(user=user, auth_mode=auth_mode)


def _require_horizons_admin(vueio_session: str | None, x_vueio_agent_key: str | None) -> _AuthCtx:
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    if ctx.user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Admin access required')
    return ctx


def _project_payload(project):
    return {
        'id': project.id,
        'slug': project.slug,
        'title': project.title,
        'description': project.description,
        'status': project.status,
        'visibility': project.visibility,
        'created_by': project.created_by,
        'created_at': project.created_at,
        'updated_at': project.updated_at,
    }


def _tracker_payload(tracker):
    return {
        'id': tracker.id,
        'project_id': tracker.project_id,
        'slug': tracker.slug,
        'name': tracker.name,
        'settings': tracker_settings_for(tracker),
        'created_at': tracker.created_at,
        'updated_at': tracker.updated_at,
    }


def _shot_payload(shot):
    return {
        'id': shot.id,
        'shot_id': shot.shot_code,
        'project_id': shot.project_id,
        'tracker_id': shot.tracker_id,
        'shot_code': shot.shot_code,
        'description': shot.description,
        'status': shot.status,
        'category': shot.category,
        'tag': shot.category,
        'assignee_user_ids': get_horizon_shot_assignee_ids(shot),
        'assignees': serialize_horizon_shot_assignees(shot),
        'assignee_user_id': shot.assignee_user_id,
        'assignee': serialize_horizon_shot_assignee(shot),
        'latest_version_label': shot.latest_version_label,
        'latest_media_asset_id': shot.latest_media_asset_id,
        'created_at': shot.created_at,
        'updated_at': shot.updated_at,
    }


def _version_payload(version):
    return {
        'id': version.id,
        'project_id': version.project_id,
        'tracker_id': version.tracker_id,
        'shot_id': version.shot_id,
        'label': version.label,
        'media_asset_id': version.media_asset_id,
        'notes': version.notes,
        'created_by': version.created_by,
        'created_at': version.created_at,
        'updated_at': version.updated_at,
    }


def _user_directory():
    return load_users()


def _grant_payload(grant):
    payload = {
        'id': grant.id,
        'project_id': grant.project_id,
        'subject_type': grant.subject_type,
        'subject_id': grant.subject_id,
        'role': grant.role,
        'created_at': grant.created_at,
        'updated_at': grant.updated_at,
    }
    if grant.subject_type == 'user_id':
        user = _user_directory().get(grant.subject_id)
        if user:
            payload['subject_display_name'] = user.get('display_name') or grant.subject_id
            payload['subject_role'] = user.get('role')
    return payload


@router.get('/api/horizons/projects')
def get_horizons_projects(vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    projects = list_visible_horizon_projects(db, ctx.user, auth_mode=ctx.auth_mode)
    return {'projects': [serialize_horizon_project(db, project, user=ctx.user) for project in projects]}


@router.post('/api/horizons/projects')
def post_horizons_project(data: HorizonProjectCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _require_horizons_admin(vueio_session, x_vueio_agent_key)
    project = create_horizon_project(
        db,
        title=data.title,
        slug=data.slug,
        description=data.description,
        status=data.status,
        visibility=data.visibility,
        created_by=ctx.user.get('id') or ctx.user.get('username'),
    )
    return _project_payload(project)


@router.get('/api/horizons/projects/{project_id}')
def get_horizons_project_route(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    project, _role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    return _project_payload(project)


@router.put('/api/horizons/projects/{project_id}')
def put_horizons_project(project_id: str, data: HorizonProjectUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    if is_restricted_horizon_artist(ctx.user, access_role):
        raise HTTPException(status_code=403, detail='Artists cannot update project settings')
    project = update_horizon_project(
        db,
        project_id,
        title=data.title,
        description=data.description,
        status=data.status,
        fields_set=set(data.model_fields_set),
    )
    return _project_payload(project)


@router.get('/api/horizons/projects/{project_id}/summary')
def get_horizons_project_summary(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    return build_horizon_project_snapshot(db, project_id, user=ctx.user, access_role=access_role, include_trackers=True, include_shots=True, include_latest_files=True)


@router.get('/api/horizons/projects/{project_id}/grants')
def get_horizons_project_grants(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='owner')
    return {'grants': [_grant_payload(grant) for grant in list_horizon_project_grants(db, project_id)]}


@router.post('/api/horizons/projects/{project_id}/grants')
def post_horizons_project_grant(project_id: str, data: HorizonProjectGrantCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='owner')
    if data.subject_type == 'user_id':
        membership = ensure_horizon_project_membership_for_user(
            db,
            project_id=project_id,
            user_ref=data.subject_id,
            role=data.role,
            allow_downgrade=True,
        )
        payload = serialize_horizon_team_user(membership['user']) or {'id': data.subject_id}
        payload.update({
            'subject_type': 'user_id',
            'subject_id': payload.get('id') or data.subject_id,
            'role': membership['role'],
            'workspace_path': membership['workspace_path'],
        })
        return payload
    grant = grant_horizon_project_access(db, project_id=project_id, subject_type=data.subject_type, subject_id=data.subject_id, role=data.role)
    return _grant_payload(grant)


@router.get('/api/horizons/projects/{project_id}/grant-candidates')
def get_horizons_project_grant_candidates(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')

    current_grants = list_horizon_project_grants(db, project_id)
    member_roles = {}
    for grant in current_grants:
        if grant.subject_type not in {'user_id', 'username'}:
            continue
        user = get_horizon_assignable_user(grant.subject_id)
        user_summary = serialize_horizon_team_user(user)
        if not user_summary:
            continue
        existing_role = member_roles.get(user_summary['id'])
        if existing_role is None or {'viewer': 1, 'editor': 2, 'owner': 3}.get(grant.role, 0) > {'viewer': 1, 'editor': 2, 'owner': 3}.get(existing_role, 0):
            member_roles[user_summary['id']] = grant.role

    assigned_counts = {
        user_id: count
        for user_id, count in (
            db.query(HorizonShotAssignee.user_id, func.count(HorizonShotAssignee.shot_id))
            .filter(HorizonShotAssignee.project_id == project_id)
            .group_by(HorizonShotAssignee.user_id)
            .all()
        )
        if user_id
    }

    candidates = []
    for user in _user_directory().values():
        summary = serialize_horizon_team_user(user)
        if not summary:
            continue
        candidates.append({
            **summary,
            'is_member': summary['id'] in member_roles,
            'project_role': member_roles.get(summary['id']),
            'assigned_shot_count': int(assigned_counts.get(summary['id'], 0)),
            'workspace_path': get_horizon_user_workspace_path(user),
        })
    candidates.sort(key=lambda item: ((item.get('role') != 'admin'), (item.get('display_name') or '').lower(), (item.get('username') or '').lower()))
    return {'candidates': candidates}


@router.delete('/api/horizons/projects/{project_id}/members/{user_id}')
def delete_horizons_project_member(project_id: str, user_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='owner')
    return remove_horizon_project_membership_for_user(db, project_id=project_id, user_ref=user_id)


@router.delete('/api/horizons/projects/{project_id}/grants/{subject_type}/{subject_id}')
def delete_horizons_project_grant(project_id: str, subject_type: str, subject_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='owner')
    removed = revoke_horizon_project_access(db, project_id=project_id, subject_type=subject_type, subject_id=subject_id)
    if not removed:
        raise HTTPException(status_code=404, detail='Grant not found')
    return {'removed': True}


@router.get('/api/horizons/projects/{project_id}/media-assets')
def get_horizons_media_assets(project_id: str, scope: str | None = None, kind: str | None = None, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    assets = list_visible_horizon_media_assets(db, project_id, user=ctx.user, access_role=access_role, scope=scope, kind=kind)
    return {'assets': [serialize_media_asset(asset) for asset in assets]}


@router.post('/api/horizons/projects/{project_id}/media-assets/declare')
def post_horizons_media_asset(project_id: str, data: HorizonMediaAssetDeclare, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    file_path = data.file_path
    storage_scope = data.storage_scope
    if is_restricted_horizon_artist(ctx.user, access_role):
        file_path = require_horizon_user_workspace_path(db, project_id, ctx.user, file_path, allow_workspace_root=False)
        if str(storage_scope or '').strip().lower() != 'project':
            raise HTTPException(status_code=403, detail='Artists can only declare project-owned workspace media')
    asset = declare_media_asset(
        db,
        project_id,
        file_path,
        storage_scope=storage_scope,
        content_hash=data.content_hash,
        file_size=data.file_size,
        modified_at=data.modified_at,
    )
    return serialize_media_asset(asset)


@router.post('/api/horizons/projects/{project_id}/folders')
def post_horizons_project_folder(project_id: str, data: HorizonProjectFolderCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    path = data.path
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path)
    result = create_horizon_project_folder(db, project_id, path)
    return {'status': 'created', **result}


@router.post('/api/horizons/projects/{project_id}/files/register')
def post_horizons_project_file_register(project_id: str, data: HorizonProjectFileRegister, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    file_path = data.file_path
    if is_restricted_horizon_artist(ctx.user, access_role):
        file_path = require_horizon_user_workspace_path(db, project_id, ctx.user, file_path, allow_workspace_root=False)
    asset = register_horizon_project_file(db, project_id, file_path)
    return {'status': 'registered', 'asset': serialize_media_asset(asset)}


@router.post('/api/horizons/projects/{project_id}/files/upload')
def post_horizons_project_file_upload(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    raise HTTPException(status_code=410, detail='Use the resumable project upload API')


@router.put('/api/horizons/projects/{project_id}/files/rename')
def put_horizons_project_file_rename(project_id: str, data: HorizonProjectFileRename, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    path = data.path
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    result = rename_horizon_project_file(db, project_id, path, new_name=data.new_name)
    asset = result.pop('asset', None)
    return {'status': 'renamed', **result, 'asset': serialize_media_asset(asset) if asset else None}


@router.put('/api/horizons/projects/{project_id}/files/move')
def put_horizons_project_file_move(project_id: str, data: dict = Body(...), vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    source_path = str(data.get('path') or '')
    target_folder = str(data.get('target_folder') or '')
    if is_restricted_horizon_artist(ctx.user, access_role):
        source_path = require_horizon_user_workspace_path(db, project_id, ctx.user, source_path, allow_workspace_root=False)
        target_folder = require_horizon_user_workspace_path(db, project_id, ctx.user, target_folder)
    result = move_horizon_project_file(
        db,
        project_id,
        source_path,
        target_folder=target_folder,
        new_name=data.get('new_name'),
    )
    asset = result.pop('asset', None)
    return {'status': 'moved', **result, 'asset': serialize_media_asset(asset) if asset else None}


@router.delete('/api/horizons/projects/{project_id}/files')
def delete_horizons_project_file(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    result = delete_horizon_project_file(db, project_id, path)
    return {'status': 'deleted', **result}


@router.put('/api/horizons/projects/{project_id}/folders/rename')
def put_horizons_project_folder_rename(project_id: str, data: HorizonProjectFolderRename, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    path = data.path
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    result = rename_horizon_project_folder(db, project_id, path, new_name=data.new_name)
    return {'status': 'renamed', **result}


@router.put('/api/horizons/projects/{project_id}/folders/move')
def put_horizons_project_folder_move(project_id: str, data: dict = Body(...), vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    source_path = str(data.get('path') or '')
    target_folder = str(data.get('target_folder') or '')
    if is_restricted_horizon_artist(ctx.user, access_role):
        source_path = require_horizon_user_workspace_path(db, project_id, ctx.user, source_path, allow_workspace_root=False)
        target_folder = require_horizon_user_workspace_path(db, project_id, ctx.user, target_folder)
    result = move_horizon_project_folder(
        db,
        project_id,
        source_path,
        target_folder=target_folder,
        new_name=data.get('new_name'),
    )
    return {'status': 'moved', **result}


@router.delete('/api/horizons/projects/{project_id}/folders')
def delete_horizons_project_folder(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    result = delete_horizon_project_folder(db, project_id, path)
    return {'status': 'deleted', **result}


@router.get('/api/horizons/projects/{project_id}/trackers', deprecated=True)
def get_horizons_trackers(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    trackers = [_tracker_payload(tracker) for tracker in list_horizon_trackers(db, project_id)]
    if is_restricted_horizon_artist(ctx.user, access_role):
        visible_tracker_ids = {
            tracker.id
            for tracker in list_horizon_trackers(db, project_id)
            if list_visible_horizon_shots(db, project_id, tracker_id=tracker.id, user=ctx.user, access_role=access_role)
        }
        trackers = [tracker for tracker in trackers if tracker['id'] in visible_tracker_ids]
    return {'trackers': trackers}


@router.post('/api/horizons/projects/{project_id}/trackers', deprecated=True)
def post_horizons_tracker(project_id: str, data: HorizonTrackerCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='admin')
    tracker = create_horizon_tracker(db, project_id=project_id, name=data.name, slug=data.slug)
    return _tracker_payload(tracker)


@router.put('/api/horizons/projects/{project_id}/trackers/{tracker_id}', deprecated=True)
def put_horizons_tracker(project_id: str, tracker_id: str, data: HorizonTrackerUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    if not data.model_fields_set:
        raise HTTPException(status_code=400, detail='No tracker changes provided')
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='admin')
    tracker = update_horizon_tracker(
        db,
        project_id,
        tracker_id,
        name=data.name,
        settings=data.settings,
        fields_set=set(data.model_fields_set),
        commit=False,
    )
    actor = build_tracker_event_actor(
        user=ctx.user,
        source='agent' if ctx.auth_mode == 'agent_key' else 'app',
    )
    create_tracker_event(
        db,
        project_id=project_id,
        tracker_id=tracker.id,
        event_type='tracker_updated',
        actor_id=actor['actor_id'],
        actor_name=actor['actor_name'] or 'Unknown',
        source=actor['source'] or 'app',
        payload={'fields': sorted(data.model_fields_set)},
    )
    db.commit()
    return _tracker_payload(tracker)


@router.get('/api/horizons/projects/{project_id}/trackers/{tracker_id}/shots', deprecated=True)
def get_horizons_tracker_shots(project_id: str, tracker_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    tracker = require_horizon_tracker_view_access(db, project_id, tracker_id, user=ctx.user, access_role=access_role)
    return {'shots': [_shot_payload(shot) for shot in list_visible_horizon_shots(db, project_id, tracker_id=tracker.id, user=ctx.user, access_role=access_role)]}


@router.post('/api/horizons/projects/{project_id}/trackers/{tracker_id}/shots', deprecated=True)
def post_horizons_tracker_shot(project_id: str, tracker_id: str, data: HorizonShotCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    if is_restricted_horizon_artist(ctx.user):
        raise HTTPException(status_code=403, detail='Artists cannot create tracker shots')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_id)
    command_ctx = _horizons_shot_context(project_id, tracker, ctx, access_role)
    result = ShotCommandService(db).create_shot(
        command_ctx,
        shot_code=data.shot_code,
        description=data.description,
        status=data.status,
        category=_shot_tag_value(data),
        assignee_user_id=data.assignee_user_id,
        assignee_user_ids=data.assignee_user_ids,
    )
    shot = result.shots[0]
    _commit_horizons_shot_result(db, result, project_id)
    return _shot_payload(shot)


@router.put('/api/horizons/projects/{project_id}/shots/{shot_id}')
def put_horizons_shot(project_id: str, shot_id: str, data: HorizonShotUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    update_fields = _shot_update_fields(data)
    if is_restricted_horizon_artist(ctx.user):
        blocked_fields = update_fields - {'status', 'category'}
        if blocked_fields:
            raise HTTPException(status_code=403, detail='Artists can only update assigned shot status and tag')
    tracker = get_horizon_tracker_by_ref(db, project_id, shot.tracker_id)
    command_ctx = _horizons_shot_context(project_id, tracker, ctx, access_role)
    result = ShotCommandService(db).update_shot(
        command_ctx,
        shot,
        description=data.description,
        status=data.status,
        category=_shot_tag_value(data),
        assignee_user_id=data.assignee_user_id,
        assignee_user_ids=data.assignee_user_ids,
        fields_set=update_fields,
    )
    shot = result.shots[0]
    _commit_horizons_shot_result(db, result, project_id)
    return _shot_payload(shot)


@router.get('/api/horizons/projects/{project_id}/shots')
def get_horizons_project_shots(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    return {'shots': [_shot_payload(shot) for shot in list_visible_horizon_shots(db, project_id, user=ctx.user, access_role=access_role)]}


@router.get('/api/horizons/projects/{project_id}/shots/{shot_id}/versions')
def get_horizons_shot_versions(project_id: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    return {'versions': [_version_payload(version) for version in list_horizon_shot_versions(db, project_id, shot_id)]}


@router.post('/api/horizons/projects/{project_id}/shots/{shot_id}/versions')
def post_horizons_shot_version(project_id: str, shot_id: str, data: HorizonShotVersionCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    tracker = get_horizon_tracker_by_ref(db, project_id, shot.tracker_id)
    command_ctx = _horizons_shot_context(project_id, tracker, ctx, access_role)
    result = ShotCommandService(db).append_version(
        command_ctx,
        shot,
        label=data.label,
        media_asset_id=data.media_asset_id,
        notes=data.notes,
        created_by=ctx.user.get('id') or ctx.user.get('username'),
    )
    version = result.versions[0]
    _commit_horizons_shot_result(db, result, project_id)
    return _version_payload(version)


@router.put('/api/horizons/projects/{project_id}/shots/{shot_id}/versions/{version_id}')
def put_horizons_shot_version(project_id: str, shot_id: str, version_id: str, data: HorizonShotVersionUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    tracker = get_horizon_tracker_by_ref(db, project_id, shot.tracker_id)
    command_ctx = _horizons_shot_context(project_id, tracker, ctx, access_role)
    result = ShotCommandService(db).update_version(
        command_ctx,
        shot,
        version_id,
        media_asset_id=data.media_asset_id,
        notes=data.notes,
        fields_set=set(data.model_fields_set),
    )
    version = result.versions[0]
    _commit_horizons_shot_result(db, result, project_id)
    return _version_payload(version)
