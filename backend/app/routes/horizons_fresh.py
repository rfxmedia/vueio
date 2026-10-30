from __future__ import annotations

import json
import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.runtime_state import executor
from app.services.scrub_sprites import queue_scrub_sprites_for_assets
from app.models import HorizonShotAssignee, HorizonShotVersion, UploadItem
from app.services.auth import (
    credential_is_current,
    get_request_agent_identity,
    get_request_user,
    load_users,
    reset_request_agent_identity,
    set_request_agent_identity,
)
from app.services.file_access import require_user_file_browser_read_access
from app.services.horizons.projects import require_horizon_project_writable
from app.services.horizons.team import revoke_horizon_project_grant_of_person
from app.services.media import MODEL_EXTENSIONS, is_image, is_video
from app.services.media_resolution import resolve_media_target
from app.services.upload_links import (
    UPLOAD_LINK_CHUNK_SIZE,
    bound_agent_identity,
    issue_upload_link_token,
    parse_content_range,
    read_upload_link_token,
    request_origin,
    upload_link_command,
)
from app.services.uploads import (
    _transaction_lock,
    append_upload_chunk,
    create_project_upload_session,
    find_upload_item,
    get_authorized_upload_session,
    project_upload_scope,
    read_limited_upload_chunk,
    revalidate_project_upload_write_access,
)
from app.services.horizons_fresh import (
    build_horizon_project_snapshot,
    create_horizon_project,
    create_horizon_project_folder,
    create_horizon_tracker,
    delete_horizon_project_file,
    delete_horizon_project_folder,
    ensure_horizon_project_membership_for_user,
    get_horizon_assignable_user,
    is_horizon_workspace_root_path,
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
from app.services.user_access import has_app_access

router = APIRouter(tags=['horizons-fresh'])


def _horizons_shot_context(project_id: str, tracker, ctx, access_role: str, *, can_delete_versions: bool = False) -> ShotCommandContext:
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
        can_delete_versions=can_delete_versions,
        can_archive_shot=False,
        restricted_artist=is_restricted_horizon_artist(ctx.user),
        event_mode='full',
    )


def _commit_horizons_shot_result(db: Session, result, project_id: str) -> None:
    for tracker_id in result.stats_dirty_tracker_ids:
        refresh_horizon_tracker_stats_cache(db, get_horizon_tracker_by_ref(db, project_id, tracker_id), commit=False)
    db.commit()
    version_asset_ids = [version.media_asset_id for version in result.versions if version.media_asset_id]
    if version_asset_ids:
        executor.submit(queue_scrub_sprites_for_assets, version_asset_ids)


class HorizonProjectCreate(BaseModel):
    title: str
    slug: str | None = Field(None, description='A short unique name. Without it, Vue.io makes one from the title.')
    description: str | None = None
    status: str | None = Field('active', description='One of: active, on_hold, archived, not_started, in_progress, waiting_review, edits_requested, done.')
    visibility: str | None = Field('private', description='private, internal or client. Vue.io stores it. It does not change who can see the project.')


class HorizonProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = Field(None, description='One of: active, on_hold, archived, not_started, in_progress, waiting_review, edits_requested, done.')


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
    status: str | None = Field(None, description='One of: not_started, in_progress, waiting_review, edits_requested, done.')
    category: str | None = Field(None, description='Old name for tag. If you send both, tag is used.')
    tag: str | None = None
    assignee_user_id: str | None = Field(None, description='Old single-assignee field. Use assignee_user_ids.')
    assignee_user_ids: list[str] | None = Field(None, description='User ids or usernames of admin or member accounts. This list replaces all assignees. An empty list removes them. New assignees get at least editor access to the project.')


class HorizonShotVersionCreate(BaseModel):
    label: str | None = Field(None, description='For example v003. Without it, the next label is used.')
    file_path: str | None = Field(None, description="A video, image or 3D file in the project, relative to the project folder. Use this or media_asset_id.")
    media_asset_id: str | None = None
    notes: str | None = None


class HorizonShotVersionUpload(BaseModel):
    filename: str = Field(description='The file name with its extension, for example SH010_comp_v003.mov. Folders in it are ignored. A video, image or 3D file.')
    size: int = Field(ge=1, description='The file size in bytes.')
    label: str | None = Field(None, max_length=100, description='For example v003. Without it, the next label is used.')
    notes: str | None = Field(None, max_length=1000, description='Version notes, up to 1000 characters.')


class HorizonShotVersionUpdate(BaseModel):
    media_asset_id: str | None = Field(None, description='A media asset of this project. The media of a published version cannot change.')
    notes: str | None = None


class HorizonProjectGrantCreate(BaseModel):
    subject_type: str = Field(description='user_id or username. Use user_id.')
    subject_id: str = Field(description='The user id or username.')
    role: str = Field('viewer', description='viewer, editor or owner.')


class HorizonMediaAssetDeclare(BaseModel):
    file_path: str = Field(description='Relative to the project folder. For storage_scope media_root, a path in shared storage.')
    storage_scope: str = Field('horizons_declared', description='For example horizons_declared, project or media_root. thumbnail, transcode and derived_artifact are refused.')
    content_hash: str | None = Field(None, description='The SHA-256 of the file, as 64 hex characters.')
    file_size: int | None = None
    modified_at: float | None = Field(None, description='Last change time of the file, in Unix seconds.')


class HorizonProjectFolderCreate(BaseModel):
    path: str = Field(description='The new folder, relative to the project folder. For example plates/raw.')


class HorizonProjectFileRegister(BaseModel):
    file_path: str = Field(description='Relative to the project folder.')


class HorizonProjectFileRename(BaseModel):
    path: str = Field(description='The file, relative to the project folder.')
    new_name: str = Field(description='The full new file name, with extension.')


class HorizonProjectFolderRename(BaseModel):
    path: str = Field(description='The folder, relative to the project folder.')
    new_name: str


class HorizonProjectFileMove(BaseModel):
    path: str = Field(description='The file, relative to the project folder.')
    target_folder: str | None = Field('', description='The folder to move to, relative to the project folder. Empty for the root.')
    new_name: str | None = Field(None, description='A new file name, with extension. Without it, the name stays.')


class HorizonProjectFolderMove(BaseModel):
    path: str = Field(description='The folder, relative to the project folder.')
    target_folder: str | None = Field('', description='The folder to move into, relative to the project folder. Empty for the root.')
    new_name: str | None = Field(None, description='A new folder name. Without it, the name stays.')


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


def _require_horizons_capability(
    vueio_session: str | None,
    x_vueio_agent_key: str | None,
    capability: str,
    detail: str,
) -> _AuthCtx:
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    if not has_app_access(ctx.user, capability):
        raise HTTPException(status_code=403, detail=detail)
    return ctx


def _require_project_content_management(db: Session, project_id: str, ctx: _AuthCtx, *, required_role: str) -> str:
    _project, access_role = require_horizon_project_access(
        db,
        project_id,
        ctx.user,
        auth_mode=ctx.auth_mode,
        required_role=required_role,
    )
    if is_restricted_horizon_artist(ctx.user, access_role):
        raise HTTPException(status_code=403, detail='Project content management access required')
    return access_role


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


@router.get('/api/horizons/projects', summary='List projects, oldest first')
def get_horizons_projects(vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the projects this person can see, oldest first.

    projects_list returns the same projects, most recently updated first.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    projects = list_visible_horizon_projects(db, ctx.user, auth_mode=ctx.auth_mode)
    return {'projects': [serialize_horizon_project(db, project, user=ctx.user) for project in projects]}


@router.post('/api/horizons/projects', summary='Create a project with a slug')
def post_horizons_project(data: HorizonProjectCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create a project in the app's own storage. This person becomes its owner.

    create_project can also set a storage location and a due date.
    """
    ctx = _require_horizons_capability(
        vueio_session,
        x_vueio_agent_key,
        'create_projects',
        'Project creation access required',
    )
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


@router.get('/api/horizons/projects/{project_id}', summary='Get basic project fields')
def get_horizons_project_route(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get the id, slug, title, description, status and visibility of a project.

    get_project also returns counts, storage state and this person's role.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    project, _role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    return _project_payload(project)


@router.put('/api/horizons/projects/{project_id}', summary='Update project title or status')
def put_horizons_project(project_id: str, data: HorizonProjectUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change the title, description or status of a project.

    Send only the fields to change. update_project can also change the due date
    and thumbnail.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    if is_restricted_horizon_artist(ctx.user, access_role):
        raise HTTPException(status_code=403, detail='Project content management access required')
    project = update_horizon_project(
        db,
        project_id,
        title=data.title,
        description=data.description,
        status=data.status,
        fields_set=set(data.model_fields_set),
    )
    return _project_payload(project)


@router.get('/api/horizons/projects/{project_id}/summary', summary='Get a project summary')
def get_horizons_project_summary(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get a project with its trackers and their shots in one call.

    Each tracker has shot counts. Each shot has its code, status, tag,
    description, assignees and latest version with its file path. Archived shots
    are left out.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    return build_horizon_project_snapshot(db, project_id, user=ctx.user, access_role=access_role, include_trackers=True, include_shots=True, include_latest_files=True)


@router.get('/api/horizons/projects/{project_id}/grants', summary='List project access grants')
def get_horizons_project_grants(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the access grants of a project.

    Each grant gives a role (viewer, editor or owner) to a user id or username.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _require_project_content_management(db, project_id, ctx, required_role='owner')
    return {'grants': [_grant_payload(grant) for grant in list_horizon_project_grants(db, project_id)]}


@router.post('/api/horizons/projects/{project_id}/grants', summary='Grant project access')
def post_horizons_project_grant(project_id: str, data: HorizonProjectGrantCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Give a person a role in a project, or change their role.

    With `subject_type` `user_id`, the person must be an admin or member
    account. Vue.io then grants the role to their user id and username, and
    creates their workspace folder. The new role replaces the old one, also if
    it is lower.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _require_project_content_management(db, project_id, ctx, required_role='owner')
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


@router.get('/api/horizons/projects/{project_id}/grant-candidates', summary='List people for project access')
def get_horizons_project_grant_candidates(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the admin and member accounts that can get access to a project.

    Each person has `is_member`, their `project_role`, the number of shots
    assigned to them in this project and their workspace folder.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _require_project_content_management(db, project_id, ctx, required_role='editor')

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


@router.delete('/api/horizons/projects/{project_id}/members/{user_id}', summary='Remove a project member')
def delete_horizons_project_member(project_id: str, user_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Remove a person from a project.

    `user_id` is the user id or username. Vue.io removes all grants of the
    person in this project. It refuses with 409 while shots in the project are
    assigned to them. Their workspace folder and files stay.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _require_project_content_management(db, project_id, ctx, required_role='owner')
    return remove_horizon_project_membership_for_user(db, project_id=project_id, user_ref=user_id)


@router.delete('/api/horizons/projects/{project_id}/grants/{subject_type}/{subject_id}', summary='Delete a project access grant')
def delete_horizons_project_grant(project_id: str, subject_type: str, subject_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete an access grant and every other grant of the same person.

    `subject_type` is `user_id` or `username`. A person can have a grant of
    each type; both are deleted, so the person has no grant left. This is the
    same as delete_horizons_project_member: it refuses with 409 while shots in
    the project are assigned to the person. The project creator keeps owner
    access.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _require_project_content_management(db, project_id, ctx, required_role='owner')
    return revoke_horizon_project_grant_of_person(db, project_id=project_id, subject_type=subject_type, subject_id=subject_id)


@router.get('/api/horizons/projects/{project_id}/media-assets', summary='List project media assets')
def get_horizons_media_assets(project_id: str, scope: str | None = None, kind: str | None = None, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the available media assets of a project, oldest first.

    A media asset is a file record with an id. Versions use it. Missing files
    are left out. `scope` filters by storage scope, for example project or
    media_root. `kind` filters by runtime, declared, linked or generated.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    assets = list_visible_horizon_media_assets(db, project_id, user=ctx.user, access_role=access_role, scope=scope, kind=kind)
    return {'assets': [serialize_media_asset(asset) for asset in assets]}


@router.post('/api/horizons/projects/{project_id}/media-assets/declare', deprecated=True, summary='Declare a media asset')
def post_horizons_media_asset(project_id: str, data: HorizonMediaAssetDeclare, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create a media asset record for an existing file without reading it.

    The file must exist. A file in shared storage (scope media_root) must be
    one you can open in the File Browser. Without a `content_hash` that
    matches the file, Vue.io marks the record unavailable when it first reads
    the file. For a file in the project folder, use
    post_horizons_project_file_register.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    file_path = (data.file_path or '').strip().strip('/')
    storage_scope = data.storage_scope
    if not file_path:
        raise HTTPException(status_code=400, detail='file_path is required')
    if is_restricted_horizon_artist(ctx.user, access_role):
        file_path = require_horizon_user_workspace_path(db, project_id, ctx.user, file_path, allow_workspace_root=False)
        if str(storage_scope or '').strip().lower() != 'project':
            raise HTTPException(status_code=403, detail='Members with review access can only use media in their workspace')
    full_path, _job_key, resolved_scope = resolve_media_target(file_path, project_id, storage_scope=storage_scope, db=db)
    if not full_path or not full_path.is_file():
        raise HTTPException(status_code=404, detail='File not found')
    if resolved_scope == 'media_root':
        # A file outside the project: only one this person may open in the File Browser.
        require_user_file_browser_read_access(ctx.user, file_path)
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


@router.post('/api/horizons/projects/{project_id}/folders', deprecated=True, summary='Create project folders')
def post_horizons_project_folder(project_id: str, data: HorizonProjectFolderCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create a folder in a project, with any missing parent folders.

    If the folder exists, nothing changes.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    path = data.path
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path)
    result = create_horizon_project_folder(db, project_id, path)
    return {'status': 'created', **result}


@router.post('/api/horizons/projects/{project_id}/files/register', deprecated=True, summary='Register a project file')
def post_horizons_project_file_register(project_id: str, data: HorizonProjectFileRegister, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Record a file in the project folder as a media asset.

    Use the asset `id` as `media_asset_id` when you add a version. If the file
    is already registered, Vue.io returns its record.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    file_path = data.file_path
    if is_restricted_horizon_artist(ctx.user, access_role):
        file_path = require_horizon_user_workspace_path(db, project_id, ctx.user, file_path, allow_workspace_root=False)
    asset = register_horizon_project_file(db, project_id, file_path)
    return {'status': 'registered', 'asset': serialize_media_asset(asset)}


@router.post('/api/horizons/projects/{project_id}/files/upload', deprecated=True)
def post_horizons_project_file_upload(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    raise HTTPException(status_code=410, detail='Use the resumable project upload API')


@router.put('/api/horizons/projects/{project_id}/files/rename', deprecated=True, summary='Rename a project file')
def put_horizons_project_file_rename(project_id: str, data: HorizonProjectFileRename, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Rename a file in a project.

    `new_name` is the full file name with its extension. Links in pages,
    comments and shares change to the new path. rename_project_file also
    renames folders.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    path = data.path
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    result = rename_horizon_project_file(db, project_id, path, new_name=data.new_name)
    asset = result.pop('asset', None)
    return {'status': 'renamed', **result, 'asset': serialize_media_asset(asset) if asset else None}


@router.put('/api/horizons/projects/{project_id}/files/move', deprecated=True, summary='Move a project file')
def put_horizons_project_file_move(project_id: str, data: HorizonProjectFileMove, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Move a file to another folder in the same project. It can also rename it.

    Paths are relative to the project folder. Vue.io creates a missing target
    folder. Links in pages, comments and shares change to the new path.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    source_path = data.path
    target_folder = data.target_folder or ''
    if is_restricted_horizon_artist(ctx.user, access_role):
        source_path = require_horizon_user_workspace_path(db, project_id, ctx.user, source_path, allow_workspace_root=False)
        target_folder = require_horizon_user_workspace_path(db, project_id, ctx.user, target_folder)
    result = move_horizon_project_file(
        db,
        project_id,
        source_path,
        target_folder=target_folder,
        new_name=data.new_name,
    )
    asset = result.pop('asset', None)
    return {'status': 'moved', **result, 'asset': serialize_media_asset(asset) if asset else None}


@router.delete('/api/horizons/projects/{project_id}/files', deprecated=True, summary='Delete a project file')
def delete_horizons_project_file(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a file from a project and from disk. This is permanent.

    `path` is relative to the project folder. Versions that use the file show it
    as missing. This is the same as delete_project_file.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    result = delete_horizon_project_file(db, project_id, path)
    return {'status': 'deleted', **result}


@router.put('/api/horizons/projects/{project_id}/folders/rename', deprecated=True, summary='Rename a project folder')
def put_horizons_project_folder_rename(project_id: str, data: HorizonProjectFolderRename, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Rename a folder in a project.

    Media records and links in pages, comments and shares change to the new
    path.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    path = data.path
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    if is_horizon_workspace_root_path(path):
        raise HTTPException(status_code=400, detail='Workspace folders are protected')
    result = rename_horizon_project_folder(db, project_id, path, new_name=data.new_name)
    return {'status': 'renamed', **result}


@router.put('/api/horizons/projects/{project_id}/folders/move', deprecated=True, summary='Move a project folder')
def put_horizons_project_folder_move(project_id: str, data: HorizonProjectFolderMove, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Move a folder into another folder of the same project. It can also rename it.

    Paths are relative to the project folder. A folder cannot move into itself.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    source_path = data.path
    target_folder = data.target_folder or ''
    if is_restricted_horizon_artist(ctx.user, access_role):
        source_path = require_horizon_user_workspace_path(db, project_id, ctx.user, source_path, allow_workspace_root=False)
        target_folder = require_horizon_user_workspace_path(db, project_id, ctx.user, target_folder)
    if is_horizon_workspace_root_path(source_path):
        raise HTTPException(status_code=400, detail='Workspace folders are protected')
    result = move_horizon_project_folder(
        db,
        project_id,
        source_path,
        target_folder=target_folder,
        new_name=data.new_name,
    )
    return {'status': 'moved', **result}


@router.delete('/api/horizons/projects/{project_id}/folders', deprecated=True, summary='Delete a project folder')
def delete_horizons_project_folder(project_id: str, path: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a project folder and all files in it from disk. This is permanent.

    `path` is relative to the project folder. Versions that use these files show
    them as missing.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    if is_restricted_horizon_artist(ctx.user, access_role):
        path = require_horizon_user_workspace_path(db, project_id, ctx.user, path, allow_workspace_root=False)
    if is_horizon_workspace_root_path(path):
        raise HTTPException(status_code=400, detail='Workspace folders are protected')
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
    _require_project_content_management(db, project_id, ctx, required_role='owner')
    tracker = create_horizon_tracker(db, project_id=project_id, name=data.name, slug=data.slug)
    return _tracker_payload(tracker)


@router.put('/api/horizons/projects/{project_id}/trackers/{tracker_id}', deprecated=True)
def put_horizons_tracker(project_id: str, tracker_id: str, data: HorizonTrackerUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    if not data.model_fields_set:
        raise HTTPException(status_code=400, detail='No tracker changes provided')
    _require_project_content_management(db, project_id, ctx, required_role='owner')
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
        raise HTTPException(status_code=403, detail='Project content management access required')
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


@router.put('/api/horizons/projects/{project_id}/shots/{shot_id}', summary='Update shot fields')
def put_horizons_shot(project_id: str, shot_id: str, data: HorizonShotUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change the description, status, tag or assignees of a shot.

    `shot_id` is the shot id or code. Send only the fields to change. The tracker
    history records each change. shot_update can also change the shot code.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    update_fields = _shot_update_fields(data)
    if is_restricted_horizon_artist(ctx.user):
        blocked_fields = update_fields - {'status', 'category'}
        if blocked_fields:
            raise HTTPException(status_code=403, detail='Members with review access can only update assigned shot status and tag')
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


@router.get('/api/horizons/projects/{project_id}/shots', summary='List all project shots')
def get_horizons_project_shots(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the shots of all trackers in a project, oldest first.

    Archived shots are left out. Each shot has its tracker id, code, status, tag,
    assignees, latest version label and latest media asset id.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    return {'shots': [_shot_payload(shot) for shot in list_visible_horizon_shots(db, project_id, user=ctx.user, access_role=access_role)]}


@router.get('/api/horizons/projects/{project_id}/shots/{shot_id}/versions', summary='List shot versions')
def get_horizons_shot_versions(project_id: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the versions of a shot, oldest first.

    `shot_id` is the shot id or code. Each version has its id, label, media asset
    id and notes.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='viewer')
    require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    return {'versions': [_version_payload(version) for version in list_horizon_shot_versions(db, project_id, shot_id)]}


@router.post('/api/horizons/projects/{project_id}/shots/{shot_id}/versions', summary='Add a version to a shot', openapi_extra={'x-mcp-tool': 'version_add'})
def post_horizons_shot_version(project_id: str, shot_id: str, data: HorizonShotVersionCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Add a new version to a shot from a file that is already in the project.

    `shot_id` is the shot id or code. The new version becomes the latest. If
    it is published at once (the tracker does not hold versions for approval)
    and the shot is in progress, not started or has edits requested, the shot
    moves to waiting_review.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    return _add_shot_version(db, project_id, shot_id, ctx, file_path=data.file_path, label=data.label, media_asset_id=data.media_asset_id, notes=data.notes)


def _add_shot_version(db: Session, project_id: str, shot_ref: str, ctx: _AuthCtx, *, file_path: str | None, label: str | None, media_asset_id: str | None = None, notes: str | None = None, upload_item: UploadItem | None = None) -> dict:
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, project_id, shot_ref, user=ctx.user, access_role=access_role)
    tracker = get_horizon_tracker_by_ref(db, project_id, shot.tracker_id)
    command_ctx = _horizons_shot_context(project_id, tracker, ctx, access_role)
    result = ShotCommandService(db).append_version(
        command_ctx,
        shot,
        file_path=file_path,
        label=label,
        media_asset_id=media_asset_id,
        notes=notes,
        created_by=ctx.user.get('id') or ctx.user.get('username'),
    )
    version = result.versions[0]
    if upload_item is not None:
        # The version and its upload receipt commit together.
        upload_item.version_upload_json = json.dumps({**json.loads(upload_item.version_upload_json), 'version_id': version.id})
    _commit_horizons_shot_result(db, result, project_id)
    return _version_payload(version)


@router.post('/api/horizons/projects/{project_id}/shots/{shot_id}/versions/upload', summary='Upload a new version', openapi_extra={'x-mcp-tool': 'version_upload'})
def post_horizons_shot_version_upload(project_id: str, shot_id: str, data: HorizonShotVersionUpload, request: Request, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Upload a file from your computer as a new version of a shot.

    `shot_id` is the shot id or code. This call does not send the file. It
    returns `command`, a shell command for bash or zsh on Linux or macOS. In
    the command, set FILE to the path of the local file, then run it. The
    command sends the file in parts of `chunk_size` bytes to `upload_url`, so
    large files work. After the last part, Vue.io adds the version as
    version_add does, and the command prints it. If the Vue.io address in the
    command is not the one you use, change it. The file goes into the project
    folder; for members with review access, into their workspace. The link
    works for 24 hours, only for this file and shot. Vue.io checks your access
    again for each part. Run the same command again to resume an interrupted
    upload or retrieve its result. For your own HTTP client, send upload_token
    in X-Vueio-Upload-Token. GET upload_url returns the current offset. POST
    upload_url finishes the version and safely returns the same result on retry.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    require_horizon_project_writable(db, project_id)
    shot = require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    filename = PurePosixPath(data.filename.replace('\\', '/')).name.strip()
    media_name = PurePosixPath(filename)
    if not is_video(media_name) and not is_image(media_name) and media_name.suffix.lower() not in MODEL_EXTENSIONS:
        raise HTTPException(status_code=400, detail='Tracker media must be an image, video, or supported 3D model')
    # Refuse a used label now, not after the whole file has been sent.
    label = (data.label or '').strip() or None
    if label and any(version.label == label for version in list_horizon_shot_versions(db, project_id, shot.id)):
        raise HTTPException(status_code=400, detail='Version label already exists on shot')
    session, items = create_project_upload_session(
        db,
        project_id=project_id,
        user=ctx.user,
        access_role=access_role,
        target_path='',
        uploader_name=ctx.user.get('display_name') or ctx.user.get('username') or 'Project uploader',
        client_batch_id=f'version-upload:{uuid.uuid4().hex}',
        manifest=[{'rel_path': filename, 'original_name': filename, 'size_bytes': data.size}],
    )
    agent = get_request_agent_identity()
    item = items[0]
    item.version_upload_json = json.dumps({
        'user_id': ctx.user['id'], 'agent_key_id': agent['key_id'] if agent else None,
        'project_id': project_id, 'shot_id': shot.id, 'label': label, 'notes': data.notes,
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


def _open_upload_link(db: Session, item_id: str, token: str):
    if read_upload_link_token(token).get('item_id') != item_id:
        raise HTTPException(status_code=403, detail='This upload credential belongs to another file')
    item = db.get(UploadItem, item_id, populate_existing=True)
    if item is None or not item.version_upload_json:
        raise HTTPException(status_code=404, detail='Upload not found')
    link = json.loads(item.version_upload_json)
    user = load_users().get(link.get('user_id') or '')
    if not user:
        raise HTTPException(status_code=403, detail='The person who made this upload link has no account now')
    agent = bound_agent_identity(db, link.get('agent_key_id'), link['user_id'])
    ctx = _AuthCtx(user=user, auth_mode='agent_key' if agent else 'session')
    # The person's current access, checked again for every chunk.
    project_id = link['project_id']
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=ctx.auth_mode, required_role='editor')
    require_horizon_shot_view_access(db, project_id, link['shot_id'], user=user, access_role=access_role)
    scope = project_upload_scope(db, project_id, user)
    session, items = get_authorized_upload_session(db, scope, session_id=item.session_id)
    if not credential_is_current(user, session.created_at):
        raise HTTPException(status_code=403, detail='This account changed. Start a new upload')
    revalidate_project_upload_write_access(db, project_id=project_id, user=user, access_role=access_role, session=session)
    item = find_upload_item(items, item_id)
    return ctx, agent, scope, session, item


def _upload_link_progress(db: Session, opened) -> dict:
    _ctx, _agent, _scope, _session, item = opened
    link = json.loads(item.version_upload_json)
    if link.get('kind') == 'extra':
        received = item.size_bytes if item.status == 'complete' else item.bytes_received
        return {'received': received, 'total': item.size_bytes, 'complete': bool(link.get('completed')),
                'file_path': item.final_path if item.status == 'complete' else None,
                'extra_id': link.get('extra_id') if link.get('completed') else None}
    received = item.bytes_received
    if item.temp_path:
        try:
            received = Path(item.temp_path).stat().st_size
        except FileNotFoundError:
            pass  # Another request may have just moved the completed file.
    version_id = link.get('version_id')
    version = db.get(HorizonShotVersion, version_id) if version_id else None
    return {'received': received, 'total': item.size_bytes, 'complete': bool(version_id),
            'file_path': item.final_path if item.status == 'complete' else None,
            'version': _version_payload(version) if version else None, 'version_id': version_id}


def _write_upload_link_chunk(db: Session, opened, start: int, chunk: bytes) -> dict:
    _ctx, _agent, scope, session, item = opened
    session, _items, item = append_upload_chunk(
        db,
        session=session,
        item=item,
        root_dir=scope.root_dir,
        offset=start,
        chunk=chunk,
        max_chunk_bytes=UPLOAD_LINK_CHUNK_SIZE,
    )
    return _finish_upload_link(db, opened) if item.status == 'complete' else _upload_link_progress(db, opened)


def _finish_upload_link(db: Session, opened) -> dict:
    ctx, agent, scope, session, item = opened
    _transaction_lock(db, f'upload-session:{session.id}')
    db.refresh(item)
    if item.status != 'complete':
        # Recover bytes written before an interrupted request could commit its offset.
        append_upload_chunk(db, session=session, item=item, root_dir=scope.root_dir, offset=item.size_bytes, chunk=b'')
        _transaction_lock(db, f'upload-session:{session.id}')
        db.refresh(item)
    link = json.loads(item.version_upload_json)
    # An extra link names its target version from the start; it is done when completed.
    done = link.get('completed') if link.get('kind') == 'extra' else link.get('version_id')
    if done:
        return _upload_link_progress(db, opened)
    # History names the person and the agent the link was made for, as for
    # any agent request.
    agent_token = set_request_agent_identity(agent)
    try:
        if link.get('kind') == 'extra':
            from app.routes.shot_extras import finish_extra_upload

            finish_extra_upload(db, link, ctx, item)
        else:
            _add_shot_version(db, link['project_id'], link['shot_id'], ctx, file_path=item.final_path,
                              label=link.get('label'), notes=link.get('notes'), upload_item=item)
    finally:
        reset_request_agent_identity(agent_token)
    return _upload_link_progress(db, opened)


@router.get('/api/upload-links/{item_id}', summary='Get upload progress')
def get_upload_link_progress(item_id: str, x_vueio_upload_token: str = Header(...), db: Session = Depends(get_db)):
    return _upload_link_progress(db, _open_upload_link(db, item_id, x_vueio_upload_token))


@router.post('/api/upload-links/{item_id}', summary='Finish an uploaded version')
def finish_upload_link(item_id: str, x_vueio_upload_token: str = Header(...), db: Session = Depends(get_db)):
    return _finish_upload_link(db, _open_upload_link(db, item_id, x_vueio_upload_token))


@router.put('/api/upload-links/{item_id}', summary='Send a chunk to an upload link')
async def put_upload_link_chunk(item_id: str, request: Request, x_vueio_upload_token: str = Header(...), content_range: str | None = Header(None, alias='Content-Range'), db: Session = Depends(get_db)):
    """Send one chunk of a file to an upload link from version_upload.

    The command from version_upload does this for you. The body is the raw
    bytes of one chunk, up to 50 MB. The Content-Range header gives its place
    in the file: `bytes start-end/total`. Send the chunks in order. Returns
    `received`, `total` and `complete`. After the last chunk, Vue.io adds the
    file as a new version and returns it in `version`. A finished upload
    returns its result. An expired credential is refused.
    """
    start, end, total = parse_content_range(content_range)
    opened = await run_in_threadpool(_open_upload_link, db, item_id, x_vueio_upload_token)
    if total != opened[-1].size_bytes:
        raise HTTPException(status_code=400, detail=f'This upload is for a file of {opened[-1].size_bytes} bytes')
    chunk = await read_limited_upload_chunk(request, max_bytes=UPLOAD_LINK_CHUNK_SIZE)
    if len(chunk) != end - start + 1:
        raise HTTPException(status_code=400, detail='The body size is not the size in the Content-Range header')
    return await run_in_threadpool(_write_upload_link_chunk, db, opened, start, chunk)


@router.delete('/api/horizons/projects/{project_id}/shots/{shot_id}/versions/{version_id}', summary='Delete a version', openapi_extra={'x-mcp-tool': 'version_delete'})
def delete_horizons_shot_version(project_id: str, shot_id: str, version_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete one version of a shot, with its comments.

    `shot_id` is the shot id or code. The media file stays in the project. As
    when a person deletes a version in the app, the other versions keep their
    order and are numbered again from 1. Project owners only; members with
    review access cannot delete versions. Records a versions_updated event.
    Returns the shot and its remaining versions.
    """
    ctx = _auth_ctx(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, ctx.user, auth_mode=ctx.auth_mode, required_role='editor')
    shot = require_horizon_shot_view_access(db, project_id, shot_id, user=ctx.user, access_role=access_role)
    tracker = get_horizon_tracker_by_ref(db, project_id, shot.tracker_id)
    # The app's rule for deleting versions, also used by shot_update.
    can_delete_versions = access_role in {'owner', 'admin'} and not is_restricted_horizon_artist(ctx.user, access_role)
    command_ctx = _horizons_shot_context(project_id, tracker, ctx, access_role, can_delete_versions=can_delete_versions)
    result = ShotCommandService(db).delete_version(command_ctx, shot, version_id, created_by=ctx.user.get('id') or ctx.user.get('username'))
    _commit_horizons_shot_result(db, result, project_id)
    return {'status': 'deleted', 'shot': _shot_payload(shot), 'versions': [_version_payload(version) for version in result.versions]}


@router.put('/api/horizons/projects/{project_id}/shots/{shot_id}/versions/{version_id}', summary='Update a shot version')
def put_horizons_shot_version(project_id: str, shot_id: str, version_id: str, data: HorizonShotVersionUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change the notes or media asset of a shot version.

    `shot_id` is the shot id or code. Send only the fields to change. A published
    version keeps its media; add a new version instead. The tracker history
    records the change.
    """
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
