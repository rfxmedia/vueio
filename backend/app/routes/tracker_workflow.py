from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import HorizonShot, HorizonShotVersion, HorizonTracker, MediaAsset
from app.runtime_state import executor
from app.services.auth import get_request_user
from app.services.download_audit import create_download_event
from app.services.horizons_fresh import (
    SHOT_STATUS_ORDER,
    create_horizon_tracker,
    can_access_horizon_shot_version_id,
    ensure_horizon_project_user_workspace,
    ensure_horizon_project_runtime_dir,
    get_horizon_shot_by_ref,
    get_horizon_tracker_by_ref,
    get_horizon_tracker_for_share,
    get_horizon_shot_assignee_ids,
    list_horizon_shot_versions,
    list_visible_horizon_shots,
    refresh_horizon_tracker_stats_cache,
    require_horizon_user_workspace_path,
    require_horizon_project_access,
    require_horizon_shot_view_access,
    require_horizon_tracker_view_access,
    serialize_horizon_shot_assignee,
    serialize_horizon_shot_assignees,
    serialize_horizon_shot_version_media,
    touch_horizon_project,
)
from app.services.horizons.version_publication import (
    VERSION_SHARE_STATE_INTERNAL,
    VERSION_SHARE_STATE_PUBLISHED,
    set_version_share_state,
    version_share_state,
    version_media_is_publishable,
)
from app.services.horizons.projects import require_horizon_project_writable
from app.services.horizon_pages import get_horizon_page_by_ref, page_allows_tracker
from app.services.shot_commands import ShotCommandActor, ShotCommandContext, ShotCommandResult, ShotCommandService
from app.services.media_pipeline import trigger_auto_hls_package, trigger_faststart_fix
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.share_access import validate_share
from app.services.uploads import write_bounded_upload
from app.services.trackers import queue_thumbnail_warmup_for_paths
from app.services.tracker_downloads import build_tracker_latest_versions_zip, start_tracker_latest_versions_zip_job
from app.services.zip_utils import get_zip_package_job, get_zip_package_job_download, get_zip_package_job_record
from app.services.tracker_events import build_tracker_event_actor, create_tracker_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=['tracker-workflow'])


def _is_project_artist(user: dict | None) -> bool:
    return bool(user and (user.get('role') or '').strip().lower() == 'artist')


def _ensure_artist_workspace_rel_path(db: Session, project_id: str, user: dict | None, path: str | None, *, allow_workspace_root: bool = True) -> str:
    return require_horizon_user_workspace_path(
        db,
        project_id,
        user,
        path,
        allow_workspace_root=allow_workspace_root,
        outside_detail='Artists can only use files inside their workspace',
        root_detail='Cannot use the workspace root',
    )


class ShotCreate(BaseModel):
    shot_id: str
    description: Optional[str] = ''
    status: str = 'not_started'
    category: Optional[str] = None
    tag: Optional[str] = None
    file_path: Optional[str] = None
    version: int = 1


class BulkShotImport(BaseModel):
    files: List[str]


class BulkVersionUpdateRequest(BaseModel):
    folder_path: str


class BulkShotStatusUpdateRequest(BaseModel):
    shot_ids: List[str]
    status: str


class BulkShotUpdateRequest(BaseModel):
    shot_ids: List[str]
    status: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    assignee_user_id: Optional[str] = None
    assignee_user_ids: Optional[List[str]] = None


class BulkShotDeleteRequest(BaseModel):
    shot_ids: List[str]


class ShotArchiveRequest(BaseModel):
    reason: Optional[str] = None


class VersionPublicationRequest(BaseModel):
    state: str


class TrackerLatestDownloadRequest(BaseModel):
    shot_ids: Optional[List[str]] = None
    filename: Optional[str] = None


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
    new_shot_id: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    file_path: Optional[str] = None
    version: Optional[int] = None
    version_notes: Optional[str] = None
    versions: Optional[List[dict]] = None
    shot_order: Optional[List[str]] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    assignee_user_id: Optional[str] = None
    assignee_user_ids: Optional[List[str]] = None
    nodePosition: Optional[dict] = None
    brief_refs: Optional[List[dict]] = None


def _shot_tag_value(data) -> Optional[str]:
    if 'tag' in getattr(data, 'model_fields_set', set()):
        return data.tag
    return getattr(data, 'category', None)


def _shot_update_fields(data) -> set[str]:
    fields = set(getattr(data, 'model_fields_set', set()))
    if 'tag' in fields:
        fields.add('category')
        fields.discard('tag')
    return fields


def _queue_bulk_hls_packages(file_paths: list[str], project_id: str | None = None):
    db = SessionLocal()
    try:
        for file_path in file_paths:
            try:
                trigger_auto_hls_package(file_path, db, project_id=project_id)
                trigger_faststart_fix(file_path, project_id=project_id)
            except Exception:
                pass
    finally:
        db.close()


def _safe_name(value: str | None, fallback: str) -> str:
    safe_value = ''.join(c for c in (value or '') if c.isalnum() or c in '._- ').strip()
    if safe_value in {'.', '..'}:
        return fallback
    return safe_value or fallback


def _version_number(value) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _next_version_label(existing_versions: list[HorizonShotVersion]) -> str:
    max_version = 0
    for version in existing_versions or []:
        parsed = _version_number(version.label)
        if parsed is not None:
            max_version = max(max_version, parsed)
    return str(max_version + 1)


def _serialize_horizon_shot(db: Session, shot: HorizonShot) -> dict:
    versions = list_horizon_shot_versions(db, shot.project_id, shot.id)
    asset_ids = [version.media_asset_id for version in versions if version.media_asset_id]
    asset_map = {}
    if asset_ids:
        asset_map = {
            asset.id: asset
            for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(asset_ids)).all()
        }

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
        'versions': [serialize_horizon_shot_version_media(version, asset_map.get(version.media_asset_id)) for version in versions],
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


def _resolve_unique_bulk_shots(shot_refs: list[str], resolver) -> list[HorizonShot]:
    shots: list[HorizonShot] = []
    seen_ids: set[str] = set()
    for shot_ref in shot_refs:
        shot = resolver(shot_ref)
        if shot.id in seen_ids:
            continue
        shots.append(shot)
        seen_ids.add(shot.id)
    return shots


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


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots')
def add_shot_to_tracker(project_id: str, tracker_name: str, data: ShotCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot create tracker shots')
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


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk')
def bulk_import_shots(project_id: str, tracker_name: str, data: BulkShotImport, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot bulk-create tracker shots')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).bulk_import_shots(ctx, data.files, created_by=user.get('id') or user.get('username'))
    imported_shots = [_serialize_horizon_shot(db, shot) for shot in result.shots]
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'imported': len(imported_shots), 'shots': imported_shots}


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-version-update')
def bulk_update_shot_versions(project_id: str, tracker_name: str, data: BulkVersionUpdateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
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


@router.put('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}')
def update_shot_in_tracker(project_id: str, tracker_name: str, shot_id: str, data: ShotUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='viewer')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    actor = _request_tracker_actor(user, auth_mode)

    if not _access_role_meets(access_role, 'editor'):
        raise HTTPException(status_code=403, detail='Editor access required')

    if data.shot_order:
        if _is_project_artist(user):
            raise HTTPException(status_code=403, detail='Artists cannot reorder tracker shots')
        ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
        result = ShotCommandService(db).reorder_shots(ctx, data.shot_order)
        _apply_shot_command_result(db, result, project_id=project_id)
        return {'status': 'reordered'}

    shot = require_horizon_shot_view_access(db, project_id, shot_id, tracker_id=tracker.id, user=user, access_role=access_role)

    old_status = shot.status
    old_shot_code = shot.shot_code
    old_description = shot.description
    old_category = shot.category
    old_assignee_user_id = shot.assignee_user_id
    old_assignee_ids = get_horizon_shot_assignee_ids(shot)
    old_assignees = serialize_horizon_shot_assignees(shot)
    update_fields: set[str] = set()
    shot_code = None
    description = None
    status = None
    category = None
    assignee_user_id = None
    assignee_user_ids = None
    incoming_fields = _shot_update_fields(data)

    ignore_unchanged_artist_assignee = False
    if _is_project_artist(user):
        artist_fields = set(incoming_fields)
        if 'assignee_user_id' in artist_fields:
            requested_assignee = data.assignee_user_id if data.assignee_user_id else None
            current_assignee = shot.assignee_user_id if shot.assignee_user_id else None
            if requested_assignee == current_assignee:
                # Older frontend bundles included the unchanged assignee on status saves.
                # Tolerate that no-op so artist editors can still change status, but
                # continue blocking actual assignment changes.
                artist_fields.remove('assignee_user_id')
                ignore_unchanged_artist_assignee = True
        if 'assignee_user_ids' in artist_fields:
            requested_assignees = [value for value in (data.assignee_user_ids or []) if value]
            if requested_assignees == old_assignee_ids:
                artist_fields.remove('assignee_user_ids')
                ignore_unchanged_artist_assignee = True
        blocked_fields = artist_fields & {'new_shot_id', 'description', 'assignee_user_id', 'assignee_user_ids', 'shot_order'}
        if blocked_fields:
            raise HTTPException(status_code=403, detail='Artists can only update shot status, tag, and versions')
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
    if 'assignee_user_ids' in data.model_fields_set and not ignore_unchanged_artist_assignee:
        assignee_user_ids = data.assignee_user_ids or []
        update_fields.add('assignee_user_ids')

    ctx = _shot_command_context(
        project_id=project_id,
        tracker=tracker,
        access_role=access_role,
        user=user,
        auth_mode=auth_mode,
        can_delete_versions=_access_role_meets(access_role, 'owner'),
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


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id}/brief/upload')
async def upload_shot_brief(project_id: str, tracker_name: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), file: UploadFile = File(...), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    if _is_project_artist(user):
        raise HTTPException(status_code=403, detail='Artists cannot upload shot briefs')
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


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-status')
def bulk_update_shot_statuses(project_id: str, tracker_name: str, data: BulkShotStatusUpdateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
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


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-update')
def bulk_update_tracker_shots(project_id: str, tracker_name: str, data: BulkShotUpdateRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    shot_refs = _normalize_bulk_shot_refs(data.shot_ids)
    update_fields = _shot_update_fields(data) - {'shot_ids'}
    allowed_fields = {'status', 'category', 'assignee_user_id', 'assignee_user_ids'}
    update_fields &= allowed_fields
    if not update_fields:
        raise HTTPException(status_code=400, detail='At least one bulk update field is required')
    if _is_project_artist(user) and update_fields - {'status', 'category'}:
        raise HTTPException(status_code=403, detail='Artists can only bulk update shot status and tag')

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
    )
    _apply_shot_command_result(db, result, project_id=project_id)
    return {
        'status': 'updated',
        'updated': result.response_hint['updated'],
        'unchanged': result.response_hint['unchanged'],
        'fields': result.response_hint['fields'],
        'shots': result.response_hint['shots'],
    }


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/bulk-delete')
def bulk_delete_shots_from_tracker(project_id: str, tracker_name: str, data: BulkShotDeleteRequest, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, _access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='owner')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role='owner', user=user, auth_mode=auth_mode, can_delete=True, can_delete_versions=True)
    result = ShotCommandService(db).bulk_delete_shots(ctx, data.shot_ids)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': 'deleted', 'deleted': len(result.deleted), 'shots': result.deleted, 'source_files_deleted': False}



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


@router.get('/api/package-jobs/{job_id}')
def get_package_job(
    job_id: str,
    share_token: str | None = None,
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
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
        event_type='download_all',
        resource_type='tracker_latest_zip',
        resource_id=tracker.id,
        resource_name=tracker.name,
        filename=data.filename,
        paths=data.shot_ids or [],
        metadata={'access_role': access_role, 'selected_shots': bool(data.shot_ids)},
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
    )


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/download-latest-zip-job')
def create_tracker_latest_versions_zip_job(project_id: str, tracker_name: str, data: TrackerLatestDownloadRequest, request: Request, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
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
        event_type='download_all',
        resource_type='tracker_latest_zip_job',
        resource_id=tracker.id,
        resource_name=tracker.name,
        filename=data.filename,
        paths=data.shot_ids or [],
        metadata={'access_role': access_role, 'selected_shots': bool(data.shot_ids)},
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


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}/archive')
def archive_shot_from_tracker(project_id: str, tracker_name: str, shot_id: str, data: ShotArchiveRequest | None = None, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).archive_shot(ctx, shot_id, reason=data.reason if data else None)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': result.response_hint.get('status', 'archived'), 'shot': _serialize_horizon_shot(db, result.shots[0])}


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id}/versions/{version_id}/publication')
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
    shot = get_horizon_shot_by_ref(db, project_id, shot_id, tracker_id=tracker.id)
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
            },
            created_at=now,
        )
        db.commit()

    return {
        'status': 'updated' if changed else 'unchanged',
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


@router.post('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}/restore')
def restore_shot_to_tracker(project_id: str, tracker_name: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role=access_role, user=user, auth_mode=auth_mode)
    result = ShotCommandService(db).restore_shot(ctx, shot_id)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': result.response_hint.get('status', 'active'), 'shot': _serialize_horizon_shot(db, result.shots[0])}


@router.delete('/api/projects/{project_id}/trackers/{tracker_name}/shots/{shot_id:path}')
def delete_shot_from_tracker(project_id: str, tracker_name: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    project, _access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='owner')
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_name)
    ctx = _shot_command_context(project_id=project_id, tracker=tracker, access_role='owner', user=user, auth_mode=auth_mode, can_delete=True, can_delete_versions=True)
    result = ShotCommandService(db).delete_shot(ctx, shot_id)
    _apply_shot_command_result(db, result, project_id=project_id)
    return {'status': 'deleted'}


@router.post('/api/projects/{project_id}/shots')
def add_shot_legacy(project_id: str, data: ShotCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor')
    _get_or_create_main_tracker(db, project_id, can_create=access_role == 'admin')
    return add_shot_to_tracker(project_id, 'Main', data, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key, db=db)


@router.put('/api/projects/{project_id}/shots/{shot_id:path}')
def update_shot_legacy(project_id: str, shot_id: str, data: ShotUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    return update_shot_in_tracker(project_id, 'Main', shot_id, data, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key, db=db)


@router.delete('/api/projects/{project_id}/shots/{shot_id:path}')
def delete_shot_legacy(project_id: str, shot_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    return delete_shot_from_tracker(project_id, 'Main', shot_id=shot_id, vueio_session=vueio_session, x_vueio_agent_key=x_vueio_agent_key, db=db)
