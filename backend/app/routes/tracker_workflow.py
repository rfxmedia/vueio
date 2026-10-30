from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import HorizonShot, HorizonShotExtra, HorizonShotExtraFile, HorizonShotVersion, HorizonTracker
from app.runtime_state import executor
from app.services.auth import get_request_user
from app.services.download_audit import create_download_event
from app.services.horizons.trackers import _serialize_horizon_versions_by_shot
from app.services.horizons_fresh import (
    SHOT_STATUS_ORDER,
    create_horizon_tracker,
    can_access_horizon_shot_version_id,
    ensure_horizon_project_runtime_dir,
    get_horizon_shot_by_ref,
    get_horizon_tracker_by_ref,
    get_horizon_tracker_for_share,
    get_horizon_shot_assignee_ids,
    list_visible_horizon_shots,
    refresh_horizon_tracker_stats_cache,
    require_horizon_user_workspace_path,
    require_horizon_project_access,
    require_horizon_shot_view_access,
    require_horizon_tracker_view_access,
    serialize_horizon_shot_assignee,
    serialize_horizon_shot_assignees,
    touch_horizon_project,
)
from app.services.horizons.version_publication import (
    VERSION_SHARE_STATE_INTERNAL,
    VERSION_SHARE_STATE_PUBLISHED,
    move_latest_published_version_to_review,
    set_version_share_state,
    version_share_state,
    version_media_is_publishable,
)
from app.services.horizons.projects import require_horizon_project_writable
from app.services.horizons.team import apply_horizon_assignee_changes
from app.services.horizon_pages import get_horizon_page_by_ref, page_allows_tracker
from app.services.shot_commands import ShotCommandActor, ShotCommandContext, ShotCommandResult, ShotCommandService
from app.services.media_pipeline import trigger_auto_hls_package
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.share_access import validate_share
from app.services.uploads import write_bounded_upload
from app.services.scrub_sprites import queue_scrub_sprites_for_assets
from app.services.trackers import queue_thumbnail_warmup_for_paths
from app.services.tracker_downloads import build_tracker_latest_versions_zip, start_tracker_latest_versions_zip_job
from app.services.zip_utils import get_zip_package_job, get_zip_package_job_download, get_zip_package_job_record
from app.services.tracker_events import build_tracker_event_actor, create_tracker_event
from app.services.tracker_history import prepare_tracker_history_mutation
from app.services.user_access import is_restricted_project_member

logger = logging.getLogger(__name__)
router = APIRouter(tags=['tracker-workflow'])


def _is_project_artist(user: dict | None) -> bool:
    return is_restricted_project_member(user)


def _require_project_content_manager(user: dict | None) -> None:
    # The interface reserves these actions for people who manage project
    # content; the server enforces it so agents cannot step around the screen.
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Only people who manage project content can do this.')


def _ensure_artist_workspace_rel_path(db: Session, project_id: str, user: dict | None, path: str | None, *, allow_workspace_root: bool = True) -> str:
    return require_horizon_user_workspace_path(
        db,
        project_id,
        user,
        path,
        allow_workspace_root=allow_workspace_root,
        outside_detail='Members with review access can only use files inside their workspace',
        root_detail='Cannot use the workspace root',
    )


class ShotCreate(BaseModel):
    shot_id: str = Field(description='The code of the new shot. It must be unique in the tracker.')
    description: Optional[str] = ''
    status: str = Field('not_started', description=f"One of: {', '.join(SHOT_STATUS_ORDER)}.")
    category: Optional[str] = Field(None, description='Old name for tag. Ignored when tag is given.')
    tag: Optional[str] = None
    file_path: Optional[str] = Field(None, description='A media file path, relative to the project folder. The file becomes the first version.')
    version: int = Field(1, description='The label number of the first version. Used only with file_path.')


class BulkShotImport(BaseModel):
    files: List[str] = Field(description='Media file paths, relative to the project folder. Each file becomes one new shot.')


class BulkVersionUpdateRequest(BaseModel):
    folder_path: str = Field(description='A folder path, relative to the project folder.')


class BulkShotStatusUpdateRequest(BaseModel):
    shot_ids: List[str] = Field(description='Shot ids or codes, up to 250.')
    status: str = Field(description=f"One of: {', '.join(SHOT_STATUS_ORDER)}.")


class BulkShotUpdateRequest(BaseModel):
    shot_ids: List[str] = Field(description='Shot ids or codes, up to 250.')
    status: Optional[str] = Field(None, description=f"One of: {', '.join(SHOT_STATUS_ORDER)}.")
    category: Optional[str] = Field(None, description='Old name for tag. Ignored when tag is given.')
    tag: Optional[str] = Field(None, description='The new tag. An empty string removes the tag.')
    assignee_user_id: Optional[str] = Field(None, description='One user id that replaces all assignees. Ignored when assignee_user_ids is given.')
    assignee_user_ids: Optional[List[str]] = Field(None, description='User ids of everyone assigned, replacing the current list. An empty list removes all assignees.')
    add_assignee_user_ids: Optional[List[str]] = Field(None, description="User ids or usernames to add to each shot's assignees. Other assignees stay. Do not send with assignee_user_ids.")
    remove_assignee_user_ids: Optional[List[str]] = Field(None, description="User ids or usernames to remove from each shot's assignees. Other assignees stay. Do not send with assignee_user_ids.")


class BulkShotDeleteRequest(BaseModel):
    shot_ids: List[str] = Field(description='Shot ids or codes, up to 250. Every shot must be archived.')


class BulkShotArchiveRequest(BaseModel):
    shot_ids: List[str] = Field(description='Shot ids or codes, up to 250.')
    reason: Optional[str] = Field(None, description='Why the shots are archived. Ignored on restore.')


class ShotArchiveRequest(BaseModel):
    reason: Optional[str] = None


class VersionPublicationRequest(BaseModel):
    state: str = Field(description="'published' shows the version on share links. 'internal' keeps it off share links.")


class TrackerTagRenameRequest(BaseModel):
    old_name: str = Field(description='The tag to rename. Case does not matter.')
    new_name: str = Field(description='The new tag name, up to 120 characters. If another tag has this name, the two tags become one.')


class TrackerTagDeleteRequest(BaseModel):
    name: str = Field(description='The tag to delete. Case does not matter.')


class TrackerLatestDownloadRequest(BaseModel):
    shot_ids: Optional[List[str]] = Field(None, description='Shot ids or codes to include. Leave out to include every shot you can see.')
    filename: Optional[str] = Field(None, description="The zip file name. '.zip' is added when it is missing.")
    include_extras: bool = Field(True, description='Include the extras of each version. A shot with extras gets a folder with its plate and extras.')
    version_id: Optional[str] = Field(None, description='Zip this one version with its extras instead of the latest version of each shot.')


def _parse_tracker_download_form_shot_ids(raw: str | None) -> list[str] | None:
    value = (raw or '').strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return [part.strip() for part in re.split(r'[\n,]+', value) if part.strip()]


class ShotUpdate(BaseModel):
    # Send only the fields to change; a field that is left out keeps its value.
    new_shot_id: Optional[str] = Field(None, description='A new shot code.')
    description: Optional[str] = None
    status: Optional[str] = Field(None, description=f"One of: {', '.join(SHOT_STATUS_ORDER)}.")
    file_path: Optional[str] = None
    version: Optional[int] = None
    version_notes: Optional[str] = None
    versions: Optional[List[dict]] = Field(None, description="The shot's full version list, replacing the current one. Read the shot first.")
    shot_order: Optional[List[str]] = Field(None, description='Every shot id of the tracker in the new order. Reorders the tracker; other fields are ignored.')
    category: Optional[str] = None
    tag: Optional[str] = Field(None, description='The shot tag. An empty string removes it.')
    assignee_user_id: Optional[str] = None
    assignee_user_ids: Optional[List[str]] = Field(None, description='User ids of everyone assigned, replacing the current list.')
    add_assignee_user_ids: Optional[List[str]] = Field(None, description='User ids or usernames to add to the current assignees. Do not send with assignee_user_ids.')
    remove_assignee_user_ids: Optional[List[str]] = Field(None, description='User ids or usernames to remove from the current assignees. Do not send with assignee_user_ids.')
    nodePosition: Optional[dict] = None
    brief_refs: Optional[List[dict]] = None
    expected_values: Optional[dict] = Field(None, description='Values read before this change. If the shot changed since, the update is refused with 409.')


def _shot_tag_value(data) -> Optional[str]:
    if 'tag' in getattr(data, 'model_fields_set', set()):
        return data.tag
    return getattr(data, 'category', None)


def _shot_update_fields(data) -> set[str]:
    fields = set(getattr(data, 'model_fields_set', set()))
    fields.discard('expected_values')
    if 'tag' in fields:
        fields.add('category')
        fields.discard('tag')
    return fields


ASSIGNEE_CHANGE_FIELDS = {'add_assignee_user_ids', 'remove_assignee_user_ids'}


def _uses_assignee_changes(fields: set[str]) -> bool:
    if not fields & ASSIGNEE_CHANGE_FIELDS:
        return False
    if fields & {'assignee_user_id', 'assignee_user_ids'}:
        raise HTTPException(status_code=400, detail='Send assignee_user_ids, or add_assignee_user_ids and remove_assignee_user_ids, not both')
    return True


def _require_expected_shot_values(shot: HorizonShot, expected: dict | None, assignee_ids: list[str]) -> None:
    if not isinstance(expected, dict):
        return
    current = {
        'shot_code': shot.shot_code,
        'description': shot.description or '',
        'status': shot.status,
        'category': shot.category or None,
        'assignee_user_ids': assignee_ids,
    }
    for field, expected_value in expected.items():
        if field not in current:
            continue
        if field == 'assignee_user_ids':
            normalized = list(dict.fromkeys(str(value) for value in (expected_value or []) if value))
            matches = normalized == current[field]
        elif field == 'description':
            matches = (expected_value or '') == current[field]
        elif field == 'category':
            matches = (expected_value or None) == current[field]
        else:
            matches = expected_value == current[field]
        if not matches:
            raise HTTPException(
                status_code=409,
                detail='This shot changed in another session. Your newer work was kept; refresh and try again.',
            )


def _queue_bulk_hls_packages(file_paths: list[str], project_id: str | None = None):
    db = SessionLocal()
    try:
        for file_path in file_paths:
            try:
                trigger_auto_hls_package(file_path, db, project_id=project_id)
            except Exception:
                pass
    finally:
        db.close()


def _safe_name(value: str | None, fallback: str) -> str:
    safe_value = ''.join(c for c in (value or '') if c.isalnum() or c in '._- ').strip()
    if safe_value in {'.', '..'}:
        return fallback
    return safe_value or fallback


def _serialize_horizon_shot(db: Session, shot: HorizonShot) -> dict:
    # The same version and extras payload as the tracker, so a saved shot keeps its extras.
    versions_by_shot, extras_by_shot = _serialize_horizon_versions_by_shot(db, shot.project_id, [shot])

    return {
        'id': shot.id,
        'shot_id': shot.shot_code,
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
        'archived_at': shot.archived_at,
        'archived_by': shot.archived_by,
        'archive_reason': shot.archive_reason,
        'versions': versions_by_shot.get(shot.id, []),
        'extras': extras_by_shot.get(shot.id, []),
        'created_at': shot.created_at,
        'updated_at': shot.updated_at,
    }


ROLE_RANK = {'viewer': 1, 'editor': 2, 'owner': 3, 'admin': 4}


def _access_role_meets(access_role: str | None, required_role: str) -> bool:
    return ROLE_RANK.get(access_role or '', 0) >= ROLE_RANK.get(required_role, 0)


def _normalize_bulk_shot_refs(shot_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for shot_id in shot_ids or []:
        value = str(shot_id or '').strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    if not normalized:
        raise HTTPException(status_code=400, detail='At least one shot is required')
    if len(normalized) > 250:
        raise HTTPException(status_code=400, detail='Bulk shot operations are limited to 250 shots')
    return normalized


def _normalize_bulk_shot_status(status: str | None) -> str:
    normalized = (status or '').strip().lower()
    if normalized not in SHOT_STATUS_ORDER:
        raise HTTPException(status_code=400, detail='Invalid shot status')
    return normalized


def _request_tracker_actor(user: dict | None, auth_mode: str | None) -> dict[str, str | None]:
    source = 'agent' if auth_mode == 'agent_key' else 'app'
    return build_tracker_event_actor(user=user, source=source)


def _shot_command_context(
    *,
    project_id: str,
    tracker: HorizonTracker,
    access_role: str,
    user: dict | None,
    auth_mode: str | None,
    can_delete: bool = False,
    can_delete_versions: bool = False,
    allowed_media_prefix: str | None = None,
) -> ShotCommandContext:
    actor = _request_tracker_actor(user, auth_mode)
    return ShotCommandContext(
        project_id=project_id,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        access_role=access_role,
        actor=ShotCommandActor(user=user, auth_mode=auth_mode, source=actor['source'], actor_id=actor['actor_id'], actor_name=actor['actor_name']),
        can_create_shot=True,
        can_update_shot=True,
        can_delete_shot=can_delete,
        can_delete_versions=can_delete_versions,
        can_archive_shot=True,
        restricted_artist=_is_project_artist(user),
        allowed_media_prefix=allowed_media_prefix,
        activity_enabled=True,
    )


def _apply_shot_command_result(db: Session, result: ShotCommandResult, *, project_id: str) -> None:
    for tracker_id in result.stats_dirty_tracker_ids:
        refresh_horizon_tracker_stats_cache(db, get_horizon_tracker_by_ref(db, project_id, tracker_id), commit=False)
    db.commit()
    if result.queued_media_paths:
        executor.submit(_queue_bulk_hls_packages, list(result.queued_media_paths), project_id)
        queue_thumbnail_warmup_for_paths(list(result.queued_media_paths), db=db, project_id=project_id, storage_scope='tracker_version')
    # Hover-scrub sheets are ready before anyone opens the tracker.
    version_asset_ids = [version.media_asset_id for version in result.versions if version.media_asset_id]
    if version_asset_ids:
        executor.submit(queue_scrub_sprites_for_assets, version_asset_ids)


def _flatten_version_payloads(data: ShotUpdate) -> list[dict]:
    return list(data.versions or []) if data.versions is not None else []


def _get_or_create_main_tracker(db: Session, project_id: str, *, can_create: bool) -> HorizonTracker:
    try:
        return get_horizon_tracker_by_ref(db, project_id, 'Main')
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    if not can_create:
        raise HTTPException(status_code=403, detail='Admin access required to create the Main tracker')
    return create_horizon_tracker(db, project_id=project_id, name='Main')


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots', summary='Create a shot')
def add_shot_to_tracker(project_id: str, tracker_name: str, data: ShotCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create a shot in a tracker, with an optional first version.

    `tracker_name` is the tracker id or name. With `file_path`, the file is
    added as the first version. Records a shot_created event in tracker
    activity. Returns the new shot.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    service = ShotCommandService(db)
    result = service.create_shot(
        ctx,
        shot_code=data.shot_id,
        description=data.description,
        status=data.status,
        category=_shot_tag_value(data),
    )
    shot = result.shots[0]
    if data.file_path:
        result.extend(service.append_version(
            ctx,
            shot,
            file_path=data.file_path,
            label=str(data.version),
            created_by=user.get('id') or user.get('username'),
        ))
        db.refresh(shot)

    _apply_shot_command_result(db, result, project_id=project_id)
    return _serialize_horizon_shot(db, shot)


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk', summary='Import shots from files')
def bulk_import_shots(project_id: str, tracker_name: str, data: BulkShotImport, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Create one shot for each media file, with the file as version 1.

    `tracker_name` is the tracker id or name. The shot code is the file name
    without its extension. If that code is in use, a suffix such as `_1` is
    added. New shots have the status not_started.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).bulk_import_shots(ctx, data.files, created_by=user.get('id') or user.get('username'))
    imported_shots = [_serialize_horizon_shot(db, shot) for shot in result.shots]
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'imported': len(imported_shots), 'shots': imported_shots}


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-version-update', summary='Add versions from a folder')
def bulk_update_shot_versions(project_id: str, tracker_name: str, data: BulkVersionUpdateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Add new versions to shots from the media files in one folder.

    `tracker_name` is the tracker id or name. Only files directly in the folder
    are read. A file matches a shot when its name without extension equals the
    shot code or the name of the latest version file, in any case. Files that a
    shot already has are skipped. The result lists files that match no shot.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    folder_path = (data.folder_path or '').strip().strip('/')
    if _is_project_artist(user):
        folder_path = _ensure_artist_workspace_rel_path(db, project_id, user, folder_path, allow_workspace_root=True)
    if not folder_path:
        raise HTTPException(status_code=400, detail='folder_path is required')
    shots = list_visible_horizon_shots(db, project_id, tracker_id=tracker.id, user=user, access_role=access_role)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode, allowed_media_prefix=folder_path if _is_project_artist(user) else None)
    result = ShotCommandService(db).bulk_update_versions_from_folder(ctx, folder_path, shots, created_by=user.get('id') or user.get('username'))
    if result.response_hint.get('updated_versions'):
        _apply_shot_command_result(db, result, project_id=project_id)
    return result.response_hint


@router.put('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}', summary='Update a shot', openapi_extra={'x-mcp-tool': 'shot_update'})
def update_shot_in_tracker(project_id: str, tracker_name: str, shot_id: str, data: ShotUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change a shot's status, tag, description, assignees or code.

    `tracker_name` is the tracker id or name and `shot_id` is the shot id or
    code. Send only the fields to change. To assign or unassign people without
    a full list, use add_assignee_user_ids and remove_assignee_user_ids.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)

    if not _access_role_meets(access_role, 'editor'):
        raise HTTPException(status_code=403, detail='Editor access required')

    if data.shot_order:
        if _is_project_artist(user):
            raise HTTPException(status_code=403, detail='Project content management access required')
        ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
        result = ShotCommandService(db).reorder_shots(ctx, data.shot_order)
        _apply_shot_command_result(db, result, project_id=project_id)
        return {'status': 'reordered'}

    # Full History restores and ordinary edits must always lock the tracker
    # before a shot row. Keeping that order prevents a restore and an edit from
    # waiting on each other in opposite directions on PostgreSQL.
    tracker = prepare_tracker_history_mutation(db, project_id=project_id, tracker_id=tracker.id)
    visible_shot = require_horizon_shot_view_access(db, project_id, shot_id, tracker_id=tracker.id, user=user, access_role=access_role)
    shot = (
        db.query(HorizonShot)
        .filter(HorizonShot.id == visible_shot.id)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShot.tracker_id == tracker.id)
        .populate_existing()
        .with_for_update()
        .one()
    )

    old_assignee_ids = get_horizon_shot_assignee_ids(shot)
    update_fields: set[str] = set()
    shot_code = None
    description = None
    status = None
    category = None
    assignee_user_id = None
    assignee_user_ids = None
    incoming_fields = _shot_update_fields(data)
    _require_expected_shot_values(shot, data.expected_values, old_assignee_ids)
    requested_assignee_ids = data.assignee_user_ids
    if _uses_assignee_changes(incoming_fields):
        # Applied to the assignees read under the shot lock, so a parallel
        # assignment is kept.
        requested_assignee_ids = apply_horizon_assignee_changes(old_assignee_ids, data.add_assignee_user_ids, data.remove_assignee_user_ids)
        incoming_fields = (incoming_fields - ASSIGNEE_CHANGE_FIELDS) | {'assignee_user_ids'}

    ignore_unchanged_artist_assignee = False
    if _is_project_artist(user):
        artist_fields = set(incoming_fields)
        if 'assignee_user_id' in artist_fields:
            requested_assignee = data.assignee_user_id if data.assignee_user_id else None
            current_assignee = shot.assignee_user_id if shot.assignee_user_id else None
            if requested_assignee == current_assignee:
                # Older frontend bundles included the unchanged assignee on status saves.
                # Tolerate that no-op so review Members can still change status, but
                # continue blocking actual assignment changes.
                artist_fields.remove('assignee_user_id')
                ignore_unchanged_artist_assignee = True
        if 'assignee_user_ids' in artist_fields:
            requested_assignees = [value for value in (requested_assignee_ids or []) if value]
            if requested_assignees == old_assignee_ids:
                artist_fields.remove('assignee_user_ids')
                ignore_unchanged_artist_assignee = True
        blocked_fields = artist_fields & {'new_shot_id', 'description', 'assignee_user_id', 'assignee_user_ids', 'shot_order'}
        if blocked_fields:
            raise HTTPException(status_code=403, detail='Members with review access can only update shot status, tag, and versions')
        if data.file_path:
            data.file_path = _ensure_artist_workspace_rel_path(db, project_id, user, data.file_path, allow_workspace_root=False)
        if data.versions is not None:
            for item in _flatten_version_payloads(data):
                file_path = (item.get('file_path') or '').strip()
                if file_path:
                    _ensure_artist_workspace_rel_path(db, project_id, user, file_path, allow_workspace_root=False)

    if data.new_shot_id and data.new_shot_id != shot.shot_code:
        shot_code = data.new_shot_id
        update_fields.add('shot_code')
    if data.description is not None:
        description = data.description
        update_fields.add('description')
    if data.status is not None:
        status = data.status
        update_fields.add('status')
    if 'category' in incoming_fields:
        tag_value = _shot_tag_value(data)
        category = tag_value if tag_value else None
        update_fields.add('category')
    if 'assignee_user_id' in data.model_fields_set and not ignore_unchanged_artist_assignee:
        assignee_user_id = data.assignee_user_id if data.assignee_user_id else None
        update_fields.add('assignee_user_id')
    if 'assignee_user_ids' in incoming_fields and not ignore_unchanged_artist_assignee:
        assignee_user_ids = requested_assignee_ids or []
        update_fields.add('assignee_user_ids')

    ctx = _shot_command_context(
        project_id=project_id,
        tracker=tracker,
        access_role=access_role,
        user=user,
        auth_mode=auth_mode,
        can_delete_versions=_access_role_meets(access_role, 'owner') and not _is_project_artist(user),
    )
    service = ShotCommandService(db)
    result = ShotCommandResult(shots=[shot])
    if update_fields:
        result = service.update_shot(
            ctx,
            shot,
            shot_code=shot_code,
            description=description,
            status=status,
            category=category,
            assignee_user_id=assignee_user_id,
            assignee_user_ids=assignee_user_ids,
            fields_set=update_fields,
        )
        shot = result.shots[0]

    if data.versions is not None:
        desired_versions = _flatten_version_payloads(data)
        result.extend(service.sync_versions(
            ctx,
            shot,
            desired_versions,
            created_by=user.get('id') or user.get('username'),
        ))
    elif data.file_path:
        requested_label = str(data.version) if data.version is not None else None
        appended = service.append_version(
            ctx,
            shot,
            file_path=data.file_path,
            label=requested_label,
            notes=data.version_notes,
            created_by=user.get('id') or user.get('username'),
        )
        result.extend(appended)
        db.refresh(shot)
    _apply_shot_command_result(db, result, project_id=project_id)

    return _serialize_horizon_shot(db, shot)


def _replace_tracker_tag(db: Session, *, project_id: str, tracker_ref: str, tag: str, new_tag: str | None, vueio_session: str | None, x_vueio_agent_key: str | None) -> dict:
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    # The permission of the app's tag list edit: editors who manage project content.
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    _require_project_content_manager(user)
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).replace_tag(ctx, tag, new_tag)
    _apply_shot_command_result(db, result, project_id=project_id)
    return result.response_hint


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/tags/rename', summary='Rename a tracker tag')
def rename_tracker_tag(project_id: str, tracker_ref: str, data: TrackerTagRenameRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Rename a tag in a tracker and on every shot that has it.

    `tracker_ref` is the tracker id or name. Archived shots change too. All
    changes are made together. Records a tracker_updated event for the tag
    list and one shots_bulk_updated event for the shots. Returns the tag list
    and the number of shots that changed.
    """
    hint = _replace_tracker_tag(db, project_id=project_id, tracker_ref=tracker_ref, tag=data.old_name, new_tag=data.new_name, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key)
    return {'status': 'renamed', **hint}


@router.post('/api/projects/{project_id}/trackers/{tracker_ref}/tags/delete', summary='Delete a tracker tag')
def delete_tracker_tag(project_id: str, tracker_ref: str, data: TrackerTagDeleteRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a tag from a tracker. Shots with the tag become untagged.

    `tracker_ref` is the tracker id or name. Archived shots change too. All
    changes are made together. Records a tracker_updated event for the tag
    list and one shots_bulk_updated event for the shots. Returns the tag list
    and the number of shots that changed.
    """
    hint = _replace_tracker_tag(db, project_id=project_id, tracker_ref=tracker_ref, tag=data.name, new_tag=None, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key)
    return {'status': 'deleted', **hint}


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id}/brief/upload', deprecated=True, summary='Upload a shot brief file')
async def upload_shot_brief(project_id: str, tracker_name: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Save a brief file for a shot in the project folder.

    `tracker_name` is the tracker id or name; `shot_id` is the shot id or code.
    The file goes to `brief/<tracker name>/<shot_id>/` in the project folder.
    The file is not linked to the shot. Records a brief_file_uploaded event.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Project content management access required')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    shot = get_horizon_shot_by_ref(db, project_id, shot_id, tracker_id=tracker.id)
    actor = _request_tracker_actor(user, auth_mode)

    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    target_dir = project_dir / 'brief' / _safe_name(tracker.name, tracker.id) / _safe_name(shot_id, shot_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(target_dir)

    safe_name = _safe_name(file.filename, f'brief_{int(time.time())}.bin')
    target_file = target_dir / safe_name
    counter = 1
    base_name = target_file.stem
    extension = target_file.suffix
    while target_file.exists():
        target_file = target_dir / f'{base_name}_{counter}{extension}'
        counter += 1

    temp_path = target_file.with_suffix('.tmp')
    bytes_written = 0
    try:
        bytes_written = await write_bounded_upload(file, temp_path, root_dir=project_dir)
        os.replace(temp_path, target_file)
        make_project_path_smb_mutable(target_file)
    except HTTPException:
        if temp_path.exists():
            temp_path.unlink()
        raise
    except Exception as exc:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        logger.error('Tracker brief upload failed (%s)', type(exc).__name__)
        raise HTTPException(status_code=500, detail='Upload failed')

    rel_path = str(target_file.relative_to(project_dir))
    touch_horizon_project(db, project_id)
    create_tracker_event(
        db,
        project_id=project_id,
        tracker_id=tracker.id,
        shot_id=shot.id,
        event_type='brief_file_uploaded',
        actor_id=actor['actor_id'],
        actor_name=actor['actor_name'],
        source=actor['source'],
        payload={
            'shot_id': shot.id,
            'shot_code': shot.shot_code,
            'file_path': rel_path,
            'file_name': safe_name,
        },
    )
    db.commit()
    return {'id': uuid.uuid4().hex[:8], 'path': rel_path, 'created_at': time.time(), 'size': bytes_written}


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-status', summary='Set the status of shots')
def bulk_update_shot_statuses(project_id: str, tracker_name: str, data: BulkShotStatusUpdateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Give many shots the same status.

    `tracker_name` is the tracker id or name. Shots that already have the
    status are counted as unchanged. Records one status_changed_bulk event.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).bulk_update_shots(ctx, data.shot_ids, fields_set={'status'}, status=data.status, event_type='status_changed_bulk')
    _apply_shot_command_result(db, result, project_id=project_id)
    return {
        'status': 'updated',
        'updated': result.response_hint['updated'],
        'unchanged': result.response_hint['unchanged'],
        'shots': result.response_hint['shots'],
    }


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-update', summary='Update shots in bulk')
def bulk_update_tracker_shots(project_id: str, tracker_name: str, data: BulkShotUpdateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Set the status, tag or assignees of many shots at once.

    `tracker_name` is the tracker id or name. Send only the fields to change.
    add_assignee_user_ids and remove_assignee_user_ids change each shot's
    assignees and keep the others. Records one shots_bulk_updated event.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    shot_refs = _normalize_bulk_shot_refs(data.shot_ids)
    update_fields = _shot_update_fields(data) - {'shot_ids'}
    changes_assignees = _uses_assignee_changes(update_fields)
    if changes_assignees:
        update_fields = (update_fields - ASSIGNEE_CHANGE_FIELDS) | {'assignee_user_ids'}
    allowed_fields = {'status', 'category', 'assignee_user_id', 'assignee_user_ids'}
    update_fields &= allowed_fields
    if not update_fields:
        raise HTTPException(status_code=400, detail='At least one bulk update field is required')
    if _is_project_artist(user) and update_fields - {'status', 'category'}:
        raise HTTPException(status_code=403, detail='Members with review access can only bulk update shot status and tag')

    next_status = _normalize_bulk_shot_status(data.status) if 'status' in update_fields else None
    next_category = None
    if 'category' in update_fields:
        raw_category = (_shot_tag_value(data) or '').strip() if _shot_tag_value(data) is not None else ''
        next_category = None if raw_category in {'', 'Uncategorized', 'Untagged'} else raw_category

    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).bulk_update_shots(
        ctx,
        shot_refs,
        fields_set=update_fields,
        status=next_status,
        category=next_category,
        assignee_user_id=data.assignee_user_id,
        assignee_user_ids=data.assignee_user_ids,
        add_assignee_user_ids=(data.add_assignee_user_ids or []) if changes_assignees else None,
        remove_assignee_user_ids=(data.remove_assignee_user_ids or []) if changes_assignees else None,
    )
    _apply_shot_command_result(db, result, project_id=project_id)
    return {
        'status': 'updated',
        'updated': result.response_hint['updated'],
        'unchanged': result.response_hint['unchanged'],
        'fields': result.response_hint['fields'],
        'shots': result.response_hint['shots'],
    }


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-delete', summary='Delete archived shots')
def bulk_delete_shots_from_tracker(project_id: str, tracker_name: str, data: BulkShotDeleteRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete archived shots with their versions, assignees and comments.

    `tracker_name` is the tracker id or name. Archive every shot first. Media
    files stay on disk. To undo, restore an earlier history point with
    restore_tracker_activity.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, _access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='owner')
    _require_project_content_manager(user)
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role='owner', user=user, auth_mode=auth_mode, can_delete=True, can_delete_versions=True)
    result = ShotCommandService(db).bulk_delete_shots(ctx, data.shot_ids)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': 'deleted', 'deleted': len(result.deleted), 'shots': result.deleted, 'source_files_deleted': False}


def _bulk_set_tracker_shots_archived(
    db: Session,
    *,
    project_id: str,
    tracker_name: str,
    data: BulkShotArchiveRequest,
    archived: bool,
    vueio_session: str | None,
    x_vueio_agent_key: str | None,
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role='editor',
    )
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(
        project_id=project_id,
        tracker=tracker,
        access_role=access_role,
        user=user,
        auth_mode=auth_mode,
    )
    result = ShotCommandService(db).bulk_set_archived(
        ctx,
        data.shot_ids,
        archived=archived,
        reason=data.reason if archived else None,
    )
    _apply_shot_command_result(db, result, project_id=project_id)
    return {
        'status': result.response_hint['status'],
        'updated': result.response_hint['updated'],
        'unchanged': result.response_hint['unchanged'],
        'shots': [_serialize_horizon_shot(db, shot) for shot in result.shots],
    }


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-archive', summary='Archive shots')
def bulk_archive_tracker_shots(
    project_id: str,
    tracker_name: str,
    data: BulkShotArchiveRequest,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Archive many shots at once.

    `tracker_name` is the tracker id or name. Archived shots leave the active
    shot list and can be restored. Shots that are already archived are counted
    as unchanged. Records one shots_bulk_updated event.
    """
    return _bulk_set_tracker_shots_archived(
        db,
        project_id=project_id,
        tracker_name=tracker_name,
        data=data,
        archived=True,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
    )


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-restore', summary='Restore archived shots')
def bulk_restore_tracker_shots(
    project_id: str,
    tracker_name: str,
    data: BulkShotArchiveRequest,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Return many archived shots to the active shot list.

    `tracker_name` is the tracker id or name. Shots that are not archived are
    counted as unchanged. Records one shots_bulk_updated event.
    """
    return _bulk_set_tracker_shots_archived(
        db,
        project_id=project_id,
        tracker_name=tracker_name,
        data=data,
        archived=False,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
    )



def _package_job_tracker_scope(job) -> tuple[str, set[str]]:
    try:
        authorization = json.loads(job.authorization_json or '{}')
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail='Package job authorization is invalid')
    if not isinstance(authorization, dict):
        raise HTTPException(status_code=403, detail='Package job authorization is invalid')

    resource_type = authorization.get('resource_type')
    if not resource_type:
        if 'tracker_id' in authorization or 'version_ids' in authorization:
            raise HTTPException(status_code=403, detail='Package job authorization is invalid')
        return '', set()
    if resource_type != 'tracker' or not job.project_id:
        raise HTTPException(status_code=403, detail='Package job authorization is invalid')

    tracker_id = authorization.get('tracker_id')
    raw_version_ids = authorization.get('version_ids')
    if (
        not isinstance(tracker_id, str)
        or not tracker_id.strip()
        or not isinstance(raw_version_ids, list)
        or not raw_version_ids
        or any(not isinstance(version_id, str) or not version_id.strip() for version_id in raw_version_ids)
    ):
        raise HTTPException(status_code=403, detail='Package job authorization is invalid')
    return tracker_id.strip(), {version_id.strip() for version_id in raw_version_ids}


def _package_job_extra_file_ids(job) -> set[str]:
    raw = json.loads(job.authorization_json or '{}').get('extra_file_ids') or []
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item.strip() for item in raw):
        raise HTTPException(status_code=403, detail='Package job authorization is invalid')
    return set(raw)


def _require_package_job_access(
    db: Session,
    job_id: str,
    *,
    vueio_session: str | None,
    x_vueio_agent_key: str | None,
    share_token: str | None,
):
    job = get_zip_package_job_record(db, job_id)
    if job.owner_type == 'share':
        share = validate_share(
            job.owner_id,
            None,
            db,
            ['file', 'folder', 'project', 'tracker', 'page'],
            share_token=share_token,
            track_access=False,
        )
        if not share.allow_download:
            raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
        if job.project_id and share.project_id != job.project_id:
            raise HTTPException(status_code=403, detail='Package job access denied')
        tracker_id, version_ids = _package_job_tracker_scope(job)
        if tracker_id:
            tracker = get_horizon_tracker_by_ref(db, job.project_id, tracker_id)
            if share.share_type == 'tracker':
                if get_horizon_tracker_for_share(db, share).id != tracker.id:
                    raise HTTPException(status_code=409, detail='This package is no longer available from this share')
            elif share.share_type == 'page':
                page = get_horizon_page_by_ref(db, job.project_id, share.page_id or '')
                if not page_allows_tracker(db, page, tracker):
                    raise HTTPException(status_code=409, detail='This package is no longer available from this page')
            elif share.share_type != 'project':
                raise HTTPException(status_code=409, detail='This package is no longer available from this share')
        if version_ids:
            published_count = (
                db.query(HorizonShotVersion)
                .filter(HorizonShotVersion.id.in_(version_ids))
                .filter(HorizonShotVersion.project_id == job.project_id)
                .filter(HorizonShotVersion.tracker_id == tracker_id)
                .filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
                .count()
            )
            if published_count != len(version_ids):
                raise HTTPException(
                    status_code=409,
                    detail='This package contains a version that is no longer shared. Request a new download.',
                )
        extra_file_ids = _package_job_extra_file_ids(job)
        if extra_file_ids:
            shared_extra_count = (
                db.query(HorizonShotExtraFile)
                .join(HorizonShotExtra, HorizonShotExtra.id == HorizonShotExtraFile.extra_id)
                .filter(HorizonShotExtraFile.id.in_(extra_file_ids))
                .filter(HorizonShotExtraFile.version_id.in_(version_ids))
                .filter(HorizonShotExtra.client_visible.is_(True))
                .count()
            )
            if shared_extra_count != len(extra_file_ids):
                raise HTTPException(
                    status_code=409,
                    detail='This package contains an extra that is no longer shared. Request a new download.',
                )
        return job, None, 'share'
    if job.owner_type != 'user':
        raise HTTPException(status_code=403, detail='Package job access denied')
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    user_id = str(user.get('id') or user.get('username') or '').strip()
    if not user_id or user_id != job.owner_id:
        raise HTTPException(status_code=404, detail='Package job not found')
    tracker_id, version_ids = _package_job_tracker_scope(job)
    if job.project_id:
        _project, access_role = require_horizon_project_access(
            db,
            job.project_id,
            user,
            auth_mode=auth_mode,
            required_role='viewer',
        )
        if tracker_id:
            require_horizon_tracker_view_access(
                db,
                job.project_id,
                tracker_id,
                user=user,
                access_role=access_role,
            )
        if version_ids:
            scoped_version_count = (
                db.query(HorizonShotVersion)
                .filter(HorizonShotVersion.id.in_(version_ids))
                .filter(HorizonShotVersion.project_id == job.project_id)
                .filter(HorizonShotVersion.tracker_id == tracker_id)
                .count()
            )
            if scoped_version_count != len(version_ids) or any(
                not can_access_horizon_shot_version_id(
                    db,
                    job.project_id,
                    version_id,
                    user=user,
                    access_role=access_role,
                )
                for version_id in version_ids
            ):
                raise HTTPException(
                    status_code=409,
                    detail='This package contains a version you can no longer access. Request a new download.',
                )
    return job, user, auth_mode


@router.get('/api/package-jobs/{job_id}', summary='Get a zip package job')
def get_package_job(
    job_id: str,
    share_token: str | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Get the progress of a zip package job.

    `status` is queued, packaging, ready or failed. When it is ready, download
    the zip with download_package_job. A job expires six hours after its last
    change. `share_token` is only for jobs started from a share link.
    """
    _require_package_job_access(
        db,
        job_id,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
        share_token=share_token,
    )
    return get_zip_package_job(job_id, db=db)


@router.get('/api/package-jobs/{job_id}/download')
def download_package_job(
    job_id: str,
    request: Request,
    share_token: str | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    _job_record, user, auth_mode = _require_package_job_access(
        db,
        job_id,
        vueio_session=vueio_session,
        x_vueio_agent_key=x_vueio_agent_key,
        share_token=share_token,
    )
    job = get_zip_package_job(job_id, db=db)
    create_download_event(
        db,
        request=request,
        user=user,
        source='package_job',
        auth_mode=auth_mode,
        share_id=_job_record.owner_id if _job_record.owner_type == 'share' else None,
        project_id=_job_record.project_id,
        event_type='download_zip',
        resource_type='package_job',
        resource_id=job_id,
        resource_name=job.get('filename') or job_id,
        filename=job.get('filename'),
        size_bytes=job.get('total_bytes'),
        metadata={
            'job_status': job.get('status'),
            'progress': job.get('progress'),
            'file_count': job.get('file_count'),
            'message': job.get('message'),
        },
    )
    return get_zip_package_job_download(job_id, db=db)


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/download-latest-zip')
def download_tracker_latest_versions_zip(project_id: str, tracker_name: str, data: TrackerLatestDownloadRequest, background_tasks: BackgroundTasks, request: Request, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    create_download_event(
        db,
        request=request,
        user=user,
        source='app',
        auth_mode=auth_mode,
        project_id=project.id,
        tracker_id=tracker.id,
        event_type='download_file' if data.version_id else 'download_all',
        resource_type='shot_version_zip' if data.version_id else 'tracker_latest_zip',
        resource_id=data.version_id or tracker.id,
        resource_name=tracker.name,
        filename=data.filename,
        paths=data.shot_ids or [],
        metadata={'access_role': access_role, 'selected_shots': bool(data.shot_ids), 'include_extras': data.include_extras},
        create_tracker_activity=True,
    )
    return build_tracker_latest_versions_zip(
        db,
        project=project,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        background_tasks=background_tasks,
        user=user,
        access_role=access_role,
        shot_refs=data.shot_ids,
        filename=data.filename,
        include_extras=data.include_extras,
        version_id=data.version_id,
    )


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/download-latest-zip-job', summary='Zip the latest versions')
def create_tracker_latest_versions_zip_job(project_id: str, tracker_name: str, data: TrackerLatestDownloadRequest, request: Request, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Start a zip of the latest version file of each shot in a tracker.

    `tracker_name` is the tracker id or name. Shots without an available file
    are skipped and counted in `skipped`. Follow the job with get_package_job
    and the returned `id`. The download is recorded in tracker activity.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    create_download_event(
        db,
        request=request,
        user=user,
        source='app',
        auth_mode=auth_mode,
        project_id=project.id,
        tracker_id=tracker.id,
        event_type='download_file' if data.version_id else 'download_all',
        resource_type='shot_version_zip' if data.version_id else 'tracker_latest_zip_job',
        resource_id=data.version_id or tracker.id,
        resource_name=tracker.name,
        filename=data.filename,
        paths=data.shot_ids or [],
        metadata={'access_role': access_role, 'selected_shots': bool(data.shot_ids), 'include_extras': data.include_extras},
        create_tracker_activity=True,
    )
    return start_tracker_latest_versions_zip_job(
        db,
        project=project,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        user=user,
        access_role=access_role,
        shot_refs=data.shot_ids,
        filename=data.filename,
        include_extras=data.include_extras,
        version_id=data.version_id,
    )


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/download-latest-zip-form')
def download_tracker_latest_versions_zip_form(
    project_id: str,
    tracker_name: str,
    background_tasks: BackgroundTasks,
    shot_ids: str | None = Form(None),
    filename: str | None = Form(None),
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    return build_tracker_latest_versions_zip(
        db,
        project=project,
        tracker_id=tracker.id,
        tracker_name=tracker.name,
        background_tasks=background_tasks,
        user=user,
        access_role=access_role,
        shot_refs=_parse_tracker_download_form_shot_ids(shot_ids),
        filename=filename,
    )


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}/archive', summary='Archive a shot')
def archive_shot_from_tracker(project_id: str, tracker_name: str, shot_id: str, data: ShotArchiveRequest | None = None, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Archive a shot. An archived shot leaves the active shot list.

    `tracker_name` is the tracker id or name; `shot_id` is the shot id or code.
    The shot keeps its versions and comments and can be restored. Records a
    shot_archived event.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).archive_shot(ctx, shot_id, reason=data.reason if data else None)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': result.response_hint.get('status', 'archived'), 'shot': _serialize_horizon_shot(db, result.shots[0])}


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id}/versions/{version_id}/publication', summary='Publish or unpublish a version')
def update_version_publication(
    project_id: str,
    tracker_name: str,
    shot_id: str,
    version_id: str,
    data: VersionPublicationRequest,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Publish a version to share links, or keep it internal.

    `tracker_name` is the tracker id or name; `shot_id` is the shot id or code.
    Publishing makes older pending versions of the shot internal. Publishing
    the latest version moves a not_started, in_progress or edits_requested
    shot to waiting_review. Only a version with available media can publish.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, _access_role = require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role='owner',
    )
    require_horizon_project_writable(db, project_id)
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    tracker = prepare_tracker_history_mutation(db, project_id=project_id, tracker_id=tracker.id)
    # Restricted owners publish only shots assigned to them, as in the interface.
    shot = require_horizon_shot_view_access(db, project_id, shot_id, tracker_id=tracker.id, user=user, access_role=_access_role)
    shot = db.query(HorizonShot).filter(HorizonShot.id == shot.id).with_for_update().one()
    version = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.id == version_id)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.tracker_id == tracker.id)
        .filter(HorizonShotVersion.shot_id == shot.id)
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail='Horizons version not found')

    target_state = str(data.state or '').strip().lower()
    if target_state not in {VERSION_SHARE_STATE_PUBLISHED, VERSION_SHARE_STATE_INTERNAL}:
        raise HTTPException(status_code=400, detail='Version state must be published or internal')
    if target_state == VERSION_SHARE_STATE_PUBLISHED:
        if not version_media_is_publishable(db, project_id, version.media_asset_id):
            raise HTTPException(
                status_code=409,
                detail='This version has no available media to publish',
            )

    previous_state = version_share_state(version)
    now = time.time()
    changed = set_version_share_state(db, version, target_state, now=now)
    is_latest_version = shot.latest_version_label == version.label
    previous_shot_status = None
    if (
        changed
        and target_state == VERSION_SHARE_STATE_PUBLISHED
        and previous_state != VERSION_SHARE_STATE_PUBLISHED
    ):
        previous_shot_status = move_latest_published_version_to_review(
            db,
            shot,
            version,
            now=now,
        )
    if changed:
        tracker.updated_at = now
        db.add(tracker)
        project.updated_at = now
        db.add(project)
        actor = _request_tracker_actor(user, auth_mode)
        event_type = (
            'version_published'
            if target_state == VERSION_SHARE_STATE_PUBLISHED
            else 'version_removed_from_shares'
            if previous_state == VERSION_SHARE_STATE_PUBLISHED
            else 'version_kept_internal'
        )
        create_tracker_event(
            db,
            project_id=project_id,
            tracker_id=tracker.id,
            shot_id=shot.id,
            shot_version_id=version.id,
            event_type=event_type,
            actor_id=actor['actor_id'],
            actor_name=actor['actor_name'] or 'Unknown',
            source=actor['source'] or 'app',
            payload={
                'shot_code': shot.shot_code,
                'version_label': version.label,
                'previous_state': previous_state,
                'share_state': target_state,
                'is_latest_version': is_latest_version,
                'shot_status_changed': previous_shot_status is not None,
                'old_status': previous_shot_status,
                'new_status': shot.status if previous_shot_status is not None else None,
            },
            created_at=now,
        )
        if previous_shot_status is not None:
            refresh_horizon_tracker_stats_cache(db, tracker, commit=False)
        db.commit()

    return {
        'status': 'updated' if changed else 'unchanged',
        'is_latest_version': is_latest_version,
        'shot_status_changed': previous_shot_status is not None,
        'previous_shot_status': previous_shot_status,
        'shot_status': shot.status,
        'versions': [
            {
                'id': item.id,
                'share_state': item.share_state,
                'published_at': item.published_at,
                'updated_at': item.updated_at,
            }
            for item in changed
        ],
    }


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}/restore', summary='Restore an archived shot')
def restore_shot_to_tracker(project_id: str, tracker_name: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return an archived shot to the active shot list.

    `tracker_name` is the tracker id or name; `shot_id` is the shot id or code.
    Records a shot_restored event.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).restore_shot(ctx, shot_id)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': result.response_hint.get('status', 'active'), 'shot': _serialize_horizon_shot(db, result.shots[0])}


@router.delete('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}', summary='Delete an archived shot')
def delete_shot_from_tracker(project_id: str, tracker_name: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete an archived shot with its versions, assignees and comments.

    `tracker_name` is the tracker id or name; `shot_id` is the shot id or code.
    Archive the shot first. Media files stay on disk. To undo, restore an
    earlier history point with restore_tracker_activity.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, _access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='owner')
    _require_project_content_manager(user)
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role='owner', user=user, auth_mode=auth_mode, can_delete=True, can_delete_versions=True)
    result = ShotCommandService(db).delete_shot(ctx, shot_id)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': 'deleted'}


@router.post('/api/projects/{project_id}/shots')
def add_shot_legacy(project_id: str, data: ShotCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    _get_or_create_main_tracker(
        db,
        project_id,
        can_create=_access_role_meets(access_role, 'owner') and not _is_project_artist(user),
    )
    return add_shot_to_tracker(project_id, 'Main', data, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key, db=db)


@router.put('/api/projects/{project_id}/shots/{shot_id:path}')
def update_shot_legacy(project_id: str, shot_id: str, data: ShotUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    return update_shot_in_tracker(project_id, 'Main', shot_id, data, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key, db=db)


@router.delete('/api/projects/{project_id}/shots/{shot_id:path}')
def delete_shot_legacy(project_id: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    return delete_shot_from_tracker(project_id, 'Main', shot_id=shot_id, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key, db=db)
