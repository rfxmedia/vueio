from __future__ import annotations

import os
import hashlib
import logging
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import UploadItem, UploadSession
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.storage_capacity import ensure_path_capacity

settings = get_settings()
logger = logging.getLogger(__name__)

UPLOAD_CHUNK_SIZE = 1 * 1024 * 1024
UPLOAD_MAX_CHUNK_SIZE = 8 * 1024 * 1024
UPLOAD_SCOPE_PROJECT = 'project_folder'
UPLOAD_SCOPE_SHARED = 'shared_folder'
TERMINAL_UPLOAD_STATUSES = {'complete', 'canceled', 'error'}
UPLOAD_MAX_REL_PATH_BYTES = 1024
UPLOAD_MAX_NAME_BYTES = 255
UPLOAD_MAX_MIME_TYPE_BYTES = 255
UPLOAD_MAX_BATCH_ID_BYTES = 200


@dataclass(frozen=True)
class AuthorizedUploadScope:
    scope_type: str
    root_dir: Path
    base_path: str
    share_id: str | None = None
    project_id: str | None = None
    owner_user_id: str | None = None


@dataclass(frozen=True)
class FinalizedUploadMove:
    final_path: str
    final_file: Path
    staging_file: Path


def normalize_upload_rel_path(value: str | None, *, allow_empty: bool = False) -> str:
    raw = str(value or '')
    if '\x00' in raw:
        raise HTTPException(status_code=400, detail='Invalid upload path')
    normalized = raw.replace('\\', '/').strip().strip('/')
    if not normalized:
        if allow_empty:
            return ''
        raise HTTPException(status_code=400, detail='Upload path is required')
    parts = [part for part in normalized.split('/') if part]
    if any(part in {'.', '..'} for part in parts):
        raise HTTPException(status_code=400, detail='Invalid upload path')
    if any(len(part.encode('utf-8')) > UPLOAD_MAX_NAME_BYTES for part in parts):
        raise HTTPException(status_code=400, detail='Upload path component is too long')
    cleaned = '/'.join(parts)
    if len(cleaned.encode('utf-8')) > UPLOAD_MAX_REL_PATH_BYTES:
        raise HTTPException(status_code=400, detail='Upload path is too long')
    if not cleaned and not allow_empty:
        raise HTTPException(status_code=400, detail='Upload path is required')
    return cleaned


def _configured_limit(value: int) -> int:
    return max(0, int(value or 0))


def _validate_manifest_file_count(manifest: list[dict], *, public: bool = False) -> None:
    max_files = _configured_limit(
        settings.PUBLIC_UPLOAD_MAX_FILES_PER_SESSION
        if public
        else settings.UPLOAD_MAX_FILES_PER_SESSION
    )
    if max_files and len(manifest) > max_files:
        raise HTTPException(status_code=413, detail='Upload manifest contains too many files')


def _validate_manifest_size_limits(manifest: list[dict], *, public: bool = False) -> None:
    _validate_manifest_file_count(manifest, public=public)
    max_file_bytes = _configured_limit(settings.UPLOAD_MAX_FILE_BYTES)
    max_session_bytes = _configured_limit(settings.UPLOAD_MAX_SESSION_BYTES)
    total_bytes = sum(int(item['size_bytes']) for item in manifest)
    for item in manifest:
        if max_file_bytes and int(item['size_bytes']) > max_file_bytes:
            raise HTTPException(status_code=413, detail=f"File exceeds the configured upload limit: {item['rel_path']}")
    if max_session_bytes and total_bytes > max_session_bytes:
        raise HTTPException(status_code=413, detail='Upload exceeds the configured session limit')


def ensure_upload_capacity(root_dir: Path, required_bytes: int = 0) -> None:
    ensure_path_capacity(
        root_dir,
        minimum_free_bytes=settings.UPLOAD_MIN_FREE_BYTES,
        required_bytes=required_bytes,
        unavailable_detail='Unable to verify upload storage capacity',
        insufficient_detail='Upload storage does not have enough free space',
    )


def _public_client_batch_id(batch_id: str, client_key: str | None) -> str:
    if not client_key:
        return batch_id
    digest = hashlib.sha256(client_key.encode('utf-8', errors='ignore')).hexdigest()[:20]
    return f'{digest}:{batch_id}'


def _transaction_lock(db: Session, key: str) -> None:
    """Serialize a small critical section when PostgreSQL is available."""
    bind = db.get_bind()
    if bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': key})


def _enforce_public_upload_concurrency(
    db: Session,
    *,
    share_id: str | None,
    client_batch_id: str,
) -> None:
    limit = _configured_limit(settings.PUBLIC_UPLOAD_MAX_ACTIVE_SESSIONS)
    if not share_id:
        return
    active = (
        db.query(UploadSession)
        .filter(UploadSession.scope_type == UPLOAD_SCOPE_SHARED)
        .filter(UploadSession.share_id == share_id)
        .filter(UploadSession.status.notin_(list(TERMINAL_UPLOAD_STATUSES | {'expired'})))
    )
    if limit and active.count() >= limit:
        raise HTTPException(status_code=429, detail='Too many active uploads for this file request')
    per_client_limit = _configured_limit(settings.PUBLIC_UPLOAD_MAX_ACTIVE_SESSIONS_PER_CLIENT)
    client_prefix = client_batch_id.partition(':')[0]
    if per_client_limit and active.filter(UploadSession.client_batch_id.like(f'{client_prefix}:%')).count() >= per_client_limit:
        raise HTTPException(status_code=429, detail='Too many active uploads from this visitor')


def _enforce_public_share_allocation(db: Session, *, share_id: str | None, additional_bytes: int) -> None:
    limit = _configured_limit(settings.PUBLIC_UPLOAD_MAX_SHARE_BYTES)
    if not limit or not share_id:
        return
    allocated = (
        db.query(func.coalesce(func.sum(UploadItem.size_bytes), 0))
        .join(UploadSession, UploadSession.id == UploadItem.session_id)
        .filter(UploadSession.scope_type == UPLOAD_SCOPE_SHARED)
        .filter(UploadSession.share_id == share_id)
        .filter(UploadSession.status.notin_(['canceled', 'expired']))
        .scalar()
    )
    if int(allocated or 0) + max(0, int(additional_bytes)) > limit:
        raise HTTPException(status_code=413, detail='This file request has reached its configured upload limit')


async def read_limited_upload_chunk(request: Request) -> bytes:
    """Read one resumable-upload chunk without buffering an unbounded body."""
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            if int(content_length) > UPLOAD_MAX_CHUNK_SIZE:
                raise HTTPException(status_code=413, detail='Chunk too large')
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='Invalid Content-Length') from exc
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > UPLOAD_MAX_CHUNK_SIZE:
            raise HTTPException(status_code=413, detail='Chunk too large')
        body.extend(part)
    return bytes(body)


def validate_uploader_name(value: str | None) -> str:
    name = ' '.join(str(value or '').strip().split())
    if not name:
        raise HTTPException(status_code=400, detail='Uploader name is required')
    if len(name) > 120:
        raise HTTPException(status_code=400, detail='Uploader name is too long')
    return name


def join_upload_path(base_path: str | None, rel_path: str | None) -> str:
    base = normalize_upload_rel_path(base_path, allow_empty=True)
    rel = normalize_upload_rel_path(rel_path, allow_empty=True)
    if not base:
        return rel
    if not rel:
        return base
    return f'{base}/{rel}'


def serialize_upload_item(item: UploadItem) -> dict:
    return {
        'id': item.id,
        'rel_path': item.rel_path,
        'original_name': item.original_name,
        'mime_type': item.mime_type,
        'size_bytes': item.size_bytes,
        'bytes_received': item.bytes_received,
        'status': item.status,
        'error_text': item.error_text,
        'final_path': item.final_path,
        'completed_at': item.completed_at,
    }


def serialize_upload_session(session: UploadSession, items: list[UploadItem]) -> dict:
    ordered_items = sorted(items, key=lambda item: (item.created_at or 0, item.original_name or '', item.id))
    return {
        'id': session.id,
        'scope_type': session.scope_type,
        'share_id': session.share_id,
        'project_id': session.project_id,
        'base_path': session.base_path,
        'uploader_name': session.uploader_name,
        'client_batch_id': session.client_batch_id,
        'status': session.status,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'last_activity_at': session.last_activity_at,
        'expires_at': session.expires_at,
        'chunk_size': UPLOAD_CHUNK_SIZE,
        'max_chunk_size': UPLOAD_MAX_CHUNK_SIZE,
        'items': [serialize_upload_item(item) for item in ordered_items],
    }


def find_upload_item(items: list[UploadItem], item_id: str) -> UploadItem:
    for item in items:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail='Upload item not found')


def serialize_upload_patch_response(session: UploadSession, item: UploadItem) -> dict:
    return {
        'session_id': session.id,
        'session_status': session.status,
        'next_offset': item.bytes_received,
        'item': {
            'id': item.id,
            'status': item.status,
            'bytes_received': item.bytes_received,
            'final_path': item.final_path,
        },
    }


def cleanup_expired_upload_sessions(db: Session) -> None:
    now = time.time()
    expired_sessions = (
        db.query(UploadSession)
        .filter(UploadSession.expires_at.isnot(None))
        .filter(UploadSession.expires_at < now)
        .filter(UploadSession.status.notin_(['complete', 'expired']))
        .all()
    )
    changed = False
    for session in expired_sessions:
        items = db.query(UploadItem).filter(UploadItem.session_id == session.id).all()
        cleanup_failed = False
        for item in items:
            if item.status == 'complete':
                continue
            try:
                _unlink_upload_temp(item)
            except HTTPException:
                logger.warning('Could not remove upload staging file for item %s; cleanup will retry', item.id)
                item.error_text = 'Could not remove upload staging file; cleanup will retry'
                item.updated_at = now
                cleanup_failed = True
                changed = True
                continue
            item.status = 'canceled'
            item.error_text = item.error_text or 'Upload session expired'
            item.updated_at = now
        if cleanup_failed:
            continue
        session.status = 'expired'
        session.updated_at = now
        session.last_activity_at = now
        changed = True
    if changed:
        db.commit()


def _create_temp_path(target_path: Path, item_id: str) -> Path:
    return target_path.parent / f'.vueio-upload-{item_id}.part'


def _unlink_upload_temp(item: UploadItem) -> None:
    if not item.temp_path:
        return
    try:
        Path(item.temp_path).unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail='Could not remove upload staging file') from exc


def _open_upload_temp(path: Path, *, exclusive: bool = False) -> int:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
    flags |= os.O_EXCL if exclusive else os.O_APPEND
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail='Upload staging path is not available') from exc
    except OSError as exc:
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server') from exc
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise HTTPException(status_code=409, detail='Upload staging path is not a regular file')
    return descriptor


def _create_empty_upload_temp(path: Path) -> None:
    descriptor = _open_upload_temp(path, exclusive=True)
    os.close(descriptor)


def _require_regular_upload_temp(path: Path) -> None:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        _create_empty_upload_temp(path)
        return
    if not stat.S_ISREG(path_stat.st_mode):
        raise HTTPException(status_code=409, detail='Upload staging path is not a regular file')


def _ensure_upload_parent_dir(target_path: Path) -> None:
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        make_project_path_smb_mutable(target_path.parent)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server') from exc
    except OSError as exc:
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server') from exc


def _target_path_for_item(root_dir: Path, final_path: str) -> Path:
    target = (root_dir / final_path).resolve()
    try:
        target.relative_to(root_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail='Upload target is outside allowed root') from exc
    return target


def _reserve_collision_path(path: Path) -> Path:
    base_name = path.stem
    suffix = path.suffix
    counter = 0
    while counter < 100000:
        candidate = path if counter == 0 else path.with_name(f'{base_name}_{counter}{suffix}')
        try:
            descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            counter += 1
            continue
        else:
            os.close(descriptor)
            return candidate
    raise HTTPException(status_code=409, detail='Unable to reserve a unique upload filename')


def _get_session_items(db: Session, session_id: str) -> list[UploadItem]:
    return (
        db.query(UploadItem)
        .filter(UploadItem.session_id == session_id)
        .order_by(UploadItem.created_at.asc(), UploadItem.original_name.asc(), UploadItem.id.asc())
        .all()
    )


def _update_session_status_from_items(session: UploadSession, items: list[UploadItem], now: float) -> None:
    active = [item for item in items if item.status not in TERMINAL_UPLOAD_STATUSES]
    if active:
        session.status = 'active'
    elif items and all(item.status == 'complete' for item in items):
        session.status = 'complete'
    elif any(item.status == 'error' for item in items):
        session.status = 'error'
    else:
        session.status = 'canceled'
    session.updated_at = now
    session.last_activity_at = now
    session.expires_at = now + _configured_limit(settings.UPLOAD_SESSION_TTL_SECONDS)


def _finalize_upload_item(
    db: Session,
    session: UploadSession,
    item: UploadItem,
    *,
    root_dir: Path,
    now: float,
) -> FinalizedUploadMove:
    desired_target = _target_path_for_item(root_dir, item.final_path or join_upload_path(session.base_path, item.rel_path))
    _ensure_upload_parent_dir(desired_target)
    actual_target = _reserve_collision_path(desired_target)
    temp_path = Path(item.temp_path or _create_temp_path(desired_target, item.id))
    try:
        _require_regular_upload_temp(temp_path)
        os.replace(temp_path, actual_target)
    except HTTPException:
        actual_target.unlink(missing_ok=True)
        raise
    except PermissionError as exc:
        actual_target.unlink(missing_ok=True)
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server') from exc
    except OSError as exc:
        actual_target.unlink(missing_ok=True)
        raise HTTPException(status_code=403, detail='Upload target is not writable by the server') from exc

    try:
        make_project_path_smb_mutable(actual_target)
        item.final_path = str(actual_target.relative_to(root_dir))
        item.temp_path = None
        item.status = 'complete'
        item.bytes_received = item.size_bytes
        item.error_text = None
        item.updated_at = now
        item.completed_at = now

        if session.scope_type == UPLOAD_SCOPE_PROJECT and session.project_id:
            from app.services.horizons_fresh import register_horizon_project_file

            register_horizon_project_file(
                db,
                session.project_id,
                item.final_path,
                commit=False,
            )
    except Exception:
        # No database change has committed yet. Put the bytes back in staging
        # so the same session can be retried without losing user data.
        db.rollback()
        try:
            if actual_target.exists() and not temp_path.exists():
                os.replace(actual_target, temp_path)
        except OSError:
            logger.exception('Could not restore upload staging file for item %s', item.id)
        raise
    return FinalizedUploadMove(
        final_path=item.final_path,
        final_file=actual_target,
        staging_file=temp_path,
    )


def _restore_finalized_uploads(moves: list[FinalizedUploadMove]) -> None:
    for move in reversed(moves):
        try:
            if move.final_file.exists() and not move.staging_file.exists():
                os.replace(move.final_file, move.staging_file)
        except OSError:
            logger.exception('Could not restore upload staging file %s', move.staging_file)


def _queue_completed_upload_warmup(
    db: Session,
    *,
    session: UploadSession,
    paths: list[str],
) -> None:
    if not paths or session.scope_type != UPLOAD_SCOPE_PROJECT or not session.project_id:
        return
    try:
        from app.services.trackers import queue_thumbnail_warmup_for_paths

        queue_thumbnail_warmup_for_paths(paths, db=db, project_id=session.project_id)
    except Exception:
        # Thumbnail generation is derived work. A warmup failure must never
        # turn a successfully committed upload into a client-visible failure.
        logger.exception('Could not queue thumbnail warmup for upload session %s', session.id)


def create_or_resume_upload_session(
    db: Session,
    *,
    scope_type: str,
    root_dir: Path,
    base_path: str,
    uploader_name: str,
    client_batch_id: str,
    manifest: list[dict],
    share_id: str | None = None,
    project_id: str | None = None,
    owner_user_id: str | None = None,
    client_key: str | None = None,
) -> tuple[UploadSession, list[UploadItem]]:
    cleanup_expired_upload_sessions(db)
    normalized_base_path = normalize_upload_rel_path(base_path, allow_empty=True)
    normalized_uploader = validate_uploader_name(uploader_name)
    batch_id = str(client_batch_id or '').strip()
    if not batch_id:
        raise HTTPException(status_code=400, detail='Client batch ID is required')
    if len(batch_id.encode('utf-8')) > UPLOAD_MAX_BATCH_ID_BYTES:
        raise HTTPException(status_code=400, detail='Client batch ID is too long')
    if not manifest:
        raise HTTPException(status_code=400, detail='Upload manifest is required')
    _validate_manifest_file_count(manifest, public=scope_type == UPLOAD_SCOPE_SHARED)
    if scope_type == UPLOAD_SCOPE_SHARED:
        batch_id = _public_client_batch_id(batch_id, client_key)

    seen_rel_paths: set[str] = set()
    normalized_manifest: list[dict] = []
    for entry in manifest:
        rel_path = normalize_upload_rel_path((entry or {}).get('rel_path') or (entry or {}).get('original_name'))
        if rel_path in seen_rel_paths:
            raise HTTPException(status_code=400, detail=f'Duplicate upload path: {rel_path}')
        seen_rel_paths.add(rel_path)
        size_bytes = int((entry or {}).get('size_bytes') or 0)
        if size_bytes < 0:
            raise HTTPException(status_code=400, detail=f'Invalid file size for {rel_path}')
        original_name = str((entry or {}).get('original_name') or Path(rel_path).name)
        mime_type = str((entry or {}).get('mime_type') or '').strip() or None
        if len(original_name.encode('utf-8')) > UPLOAD_MAX_NAME_BYTES:
            raise HTTPException(status_code=400, detail='Upload filename is too long')
        if mime_type and len(mime_type.encode('utf-8')) > UPLOAD_MAX_MIME_TYPE_BYTES:
            raise HTTPException(status_code=400, detail='Upload MIME type is too long')
        normalized_manifest.append({
            'rel_path': rel_path,
            'original_name': original_name,
            'mime_type': mime_type,
            'size_bytes': size_bytes,
        })
    _validate_manifest_size_limits(normalized_manifest, public=scope_type == UPLOAD_SCOPE_SHARED)

    if scope_type == UPLOAD_SCOPE_SHARED and share_id:
        _transaction_lock(db, f'public-upload-share:{share_id}')

    existing_session = (
        db.query(UploadSession)
        .filter(UploadSession.scope_type == scope_type)
        .filter(UploadSession.client_batch_id == batch_id)
        .filter(UploadSession.base_path == normalized_base_path)
        .filter(UploadSession.uploader_name == normalized_uploader)
        .filter(UploadSession.share_id == share_id if share_id is not None else UploadSession.share_id.is_(None))
        .filter(UploadSession.project_id == project_id if project_id is not None else UploadSession.project_id.is_(None))
        .filter(
            UploadSession.owner_user_id == owner_user_id
            if owner_user_id is not None
            else UploadSession.owner_user_id.is_(None)
        )
        .order_by(UploadSession.created_at.desc())
        .first()
    )

    now = time.time()
    if existing_session:
        existing_items = _get_session_items(db, existing_session.id)
        existing_by_rel = {item.rel_path: item for item in existing_items}
        prospective_manifest = [
            {'rel_path': item.rel_path, 'size_bytes': item.size_bytes}
            for item in existing_items
        ]
        prospective_manifest.extend(
            item for item in normalized_manifest
            if item['rel_path'] not in existing_by_rel
        )
        _validate_manifest_size_limits(prospective_manifest, public=scope_type == UPLOAD_SCOPE_SHARED)
        remaining_bytes = sum(
            max(0, int(item.size_bytes) - int(item.bytes_received or 0))
            for item in existing_items
        ) + sum(
            int(item['size_bytes'])
            for item in normalized_manifest
            if item['rel_path'] not in existing_by_rel
        )
        if scope_type == UPLOAD_SCOPE_SHARED:
            _enforce_public_share_allocation(
                db,
                share_id=share_id,
                additional_bytes=sum(
                    int(item['size_bytes'])
                    for item in normalized_manifest
                    if item['rel_path'] not in existing_by_rel
                ),
            )
        ensure_upload_capacity(root_dir, remaining_bytes)
        added = False
        for manifest_item in normalized_manifest:
            if manifest_item['rel_path'] in existing_by_rel:
                continue
            final_path = join_upload_path(normalized_base_path, manifest_item['rel_path'])
            target_path = _target_path_for_item(root_dir, final_path)
            item_id = uuid.uuid4().hex
            upload_item = UploadItem(
                id=item_id,
                session_id=existing_session.id,
                rel_path=manifest_item['rel_path'],
                original_name=manifest_item['original_name'],
                mime_type=manifest_item['mime_type'],
                size_bytes=manifest_item['size_bytes'],
                bytes_received=0,
                temp_path=str(_create_temp_path(target_path, item_id)),
                final_path=final_path,
                status='pending',
                created_at=now,
                updated_at=now,
            )
            db.add(upload_item)
            existing_items.append(upload_item)
            added = True
        _update_session_status_from_items(existing_session, existing_items, now)
        if added:
            db.commit()
        return existing_session, _get_session_items(db, existing_session.id)

    if scope_type == UPLOAD_SCOPE_SHARED:
        _enforce_public_upload_concurrency(db, share_id=share_id, client_batch_id=batch_id)
        _enforce_public_share_allocation(
            db,
            share_id=share_id,
            additional_bytes=sum(item['size_bytes'] for item in normalized_manifest),
        )
    ensure_upload_capacity(root_dir, sum(item['size_bytes'] for item in normalized_manifest))

    session = UploadSession(
        id=uuid.uuid4().hex,
        scope_type=scope_type,
        share_id=share_id,
        project_id=project_id,
        owner_user_id=owner_user_id,
        base_path=normalized_base_path,
        uploader_name=normalized_uploader,
        client_batch_id=batch_id,
        status='active',
        created_at=now,
        updated_at=now,
        last_activity_at=now,
        expires_at=now + _configured_limit(settings.UPLOAD_SESSION_TTL_SECONDS),
    )
    db.add(session)

    items: list[UploadItem] = []
    for manifest_item in normalized_manifest:
        final_path = join_upload_path(normalized_base_path, manifest_item['rel_path'])
        target_path = _target_path_for_item(root_dir, final_path)
        item_id = uuid.uuid4().hex
        upload_item = UploadItem(
            id=item_id,
            session_id=session.id,
            rel_path=manifest_item['rel_path'],
            original_name=manifest_item['original_name'],
            mime_type=manifest_item['mime_type'],
            size_bytes=manifest_item['size_bytes'],
            bytes_received=0,
            temp_path=str(_create_temp_path(target_path, item_id)),
            final_path=final_path,
            status='pending',
            created_at=now,
            updated_at=now,
        )
        db.add(upload_item)
        items.append(upload_item)

    db.flush()
    completed_moves: list[FinalizedUploadMove] = []
    try:
        for item in items:
            if item.size_bytes == 0:
                _ensure_upload_parent_dir(Path(item.temp_path))
                _create_empty_upload_temp(Path(item.temp_path))
                completed_moves.append(
                    _finalize_upload_item(db, session, item, root_dir=root_dir, now=now)
                )
        _update_session_status_from_items(session, items, now)
        db.commit()
    except Exception:
        db.rollback()
        _restore_finalized_uploads(completed_moves)
        raise
    _queue_completed_upload_warmup(
        db,
        session=session,
        paths=[move.final_path for move in completed_moves],
    )
    return session, _get_session_items(db, session.id)


def get_upload_session_for_scope(
    db: Session,
    *,
    session_id: str,
    scope_type: str,
    share_id: str | None = None,
    project_id: str | None = None,
    owner_user_id: str | None = None,
) -> tuple[UploadSession, list[UploadItem]]:
    cleanup_expired_upload_sessions(db)
    session = (
        db.query(UploadSession)
        .filter(UploadSession.id == session_id)
        .filter(UploadSession.scope_type == scope_type)
        .filter(UploadSession.share_id == share_id if share_id is not None else UploadSession.share_id.is_(None))
        .filter(UploadSession.project_id == project_id if project_id is not None else UploadSession.project_id.is_(None))
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail='Upload session not found')
    if session.owner_user_id != owner_user_id:
        raise HTTPException(status_code=404, detail='Upload session not found')
    return session, _get_session_items(db, session.id)


def append_upload_chunk(
    db: Session,
    *,
    session: UploadSession,
    item: UploadItem,
    root_dir: Path,
    offset: int,
    chunk: bytes,
) -> tuple[UploadSession, list[UploadItem], UploadItem]:
    _transaction_lock(db, f'upload-session:{session.id}')
    _transaction_lock(db, f'upload-item:{item.id}')
    db.refresh(session)
    db.refresh(item)
    now = time.time()
    if session.status in {'canceled', 'expired'}:
        raise HTTPException(status_code=409, detail='Upload session is no longer active')
    if item.status == 'complete':
        items = _get_session_items(db, session.id)
        return session, items, item
    if item.status == 'canceled':
        raise HTTPException(status_code=409, detail='Upload item was canceled')
    if item.size_bytes and len(chunk) > UPLOAD_MAX_CHUNK_SIZE:
        raise HTTPException(status_code=413, detail='Upload chunk is too large')
    if not chunk:
        raise HTTPException(status_code=400, detail='Upload chunk cannot be empty')

    temp_path = Path(item.temp_path or _create_temp_path(_target_path_for_item(root_dir, item.final_path or join_upload_path(session.base_path, item.rel_path)), item.id))
    _ensure_upload_parent_dir(temp_path)
    descriptor = _open_upload_temp(temp_path)
    try:
        current_size = os.fstat(descriptor).st_size
        if current_size != item.bytes_received:
            item.bytes_received = current_size
        if offset != item.bytes_received:
            raise HTTPException(status_code=409, detail={'message': 'Upload offset mismatch', 'expected_offset': item.bytes_received})
        if item.size_bytes and offset + len(chunk) > item.size_bytes:
            raise HTTPException(status_code=400, detail='Chunk exceeds declared file size')
        ensure_upload_capacity(root_dir, len(chunk))
        with os.fdopen(descriptor, 'ab', buffering=0) as handle:
            descriptor = -1
            handle.write(chunk)
        item.bytes_received += len(chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    item.temp_path = str(temp_path)
    item.status = 'uploading'
    item.updated_at = now
    item.error_text = None

    completed_move: FinalizedUploadMove | None = None
    if item.bytes_received == item.size_bytes:
        completed_move = _finalize_upload_item(
            db,
            session,
            item,
            root_dir=root_dir,
            now=now,
        )

    items = _get_session_items(db, session.id)
    _update_session_status_from_items(session, items, now)
    try:
        db.commit()
    except Exception:
        db.rollback()
        if completed_move is not None:
            _restore_finalized_uploads([completed_move])
        raise
    _queue_completed_upload_warmup(
        db,
        session=session,
        paths=[completed_move.final_path] if completed_move else [],
    )
    return session, items, item


async def write_bounded_upload(file: UploadFile, target_path: Path, *, root_dir: Path) -> int:
    """Stream a legacy multipart upload through the current size/space policy."""
    _ensure_upload_parent_dir(target_path)
    descriptor = _open_upload_temp(target_path, exclusive=True)
    bytes_written = 0
    max_bytes = _configured_limit(settings.UPLOAD_MAX_FILE_BYTES)
    try:
        with os.fdopen(descriptor, 'wb', buffering=0) as handle:
            descriptor = -1
            while chunk := await file.read(UPLOAD_MAX_CHUNK_SIZE):
                if max_bytes and bytes_written + len(chunk) > max_bytes:
                    raise HTTPException(status_code=413, detail='File exceeds the configured upload limit')
                ensure_upload_capacity(root_dir, len(chunk))
                handle.write(chunk)
                bytes_written += len(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return bytes_written


def cancel_upload_item(db: Session, *, session: UploadSession, item: UploadItem) -> tuple[UploadSession, list[UploadItem]]:
    _transaction_lock(db, f'upload-session:{session.id}')
    _transaction_lock(db, f'upload-item:{item.id}')
    db.refresh(session)
    db.refresh(item)
    now = time.time()
    _unlink_upload_temp(item)
    item.status = 'canceled'
    item.error_text = None
    item.updated_at = now
    items = _get_session_items(db, session.id)
    _update_session_status_from_items(session, items, now)
    db.commit()
    return session, items


def cancel_upload_session(db: Session, *, session: UploadSession) -> tuple[UploadSession, list[UploadItem]]:
    _transaction_lock(db, f'upload-session:{session.id}')
    db.refresh(session)
    now = time.time()
    items = _get_session_items(db, session.id)
    for item in items:
        if item.status == 'complete':
            continue
        _unlink_upload_temp(item)
        item.status = 'canceled'
        item.error_text = None
        item.updated_at = now
    _update_session_status_from_items(session, items, now)
    db.commit()
    return session, items


def create_authorized_upload_session(
    db: Session,
    scope: AuthorizedUploadScope,
    *,
    uploader_name: str,
    client_batch_id: str,
    manifest: list[dict],
    client_key: str | None = None,
) -> tuple[UploadSession, list[UploadItem]]:
    return create_or_resume_upload_session(
        db,
        scope_type=scope.scope_type,
        root_dir=scope.root_dir,
        base_path=scope.base_path,
        uploader_name=uploader_name,
        client_batch_id=client_batch_id,
        manifest=manifest,
        share_id=scope.share_id,
        project_id=scope.project_id,
        owner_user_id=scope.owner_user_id,
        client_key=client_key,
    )


def get_authorized_upload_session(db: Session, scope: AuthorizedUploadScope, *, session_id: str) -> tuple[UploadSession, list[UploadItem]]:
    return get_upload_session_for_scope(
        db,
        session_id=session_id,
        scope_type=scope.scope_type,
        share_id=scope.share_id,
        project_id=scope.project_id,
        owner_user_id=scope.owner_user_id,
    )


def append_authorized_upload_chunk(
    db: Session,
    scope: AuthorizedUploadScope,
    *,
    session: UploadSession,
    item: UploadItem,
    offset: int,
    chunk: bytes,
) -> tuple[UploadSession, list[UploadItem], UploadItem]:
    return append_upload_chunk(db, session=session, item=item, root_dir=scope.root_dir, offset=offset, chunk=chunk)


def cancel_authorized_upload_item(db: Session, scope: AuthorizedUploadScope, *, session: UploadSession, item: UploadItem) -> tuple[UploadSession, list[UploadItem]]:
    return cancel_upload_item(db, session=session, item=item)


def cancel_authorized_upload_session(db: Session, scope: AuthorizedUploadScope, *, session: UploadSession) -> tuple[UploadSession, list[UploadItem]]:
    return cancel_upload_session(db, session=session)


def get_latest_upload_metadata(
    db: Session,
    *,
    scope_type: str,
    final_path: str,
    project_id: str | None = None,
) -> dict | None:
    normalized_final_path = normalize_upload_rel_path(final_path, allow_empty=True)
    if not normalized_final_path:
        return None
    query = (
        db.query(UploadItem, UploadSession)
        .join(UploadSession, UploadSession.id == UploadItem.session_id)
        .filter(UploadItem.final_path == normalized_final_path)
        .filter(UploadItem.status == 'complete')
        .filter(UploadSession.scope_type == scope_type)
    )
    if project_id is not None:
        query = query.filter(UploadSession.project_id == project_id)
    result = (
        query.order_by(UploadItem.completed_at.desc().nullslast(), UploadItem.updated_at.desc(), UploadItem.id.desc())
        .first()
    )
    if result is None:
        return None
    item, session = result
    return {
        'uploaded_by': session.uploader_name,
        'uploaded_at': item.completed_at or item.updated_at or session.updated_at,
        'upload_session_id': session.id,
    }
