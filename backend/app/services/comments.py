from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Comment, HorizonPage, HorizonProject, HorizonShotVersion, MediaAsset
from app.services.file_access import require_file_browser_read_access
from app.services.horizons_fresh import (
    can_access_horizon_media_asset_id,
    can_access_horizon_shot_version_id,
    get_horizon_media_asset_by_path,
    is_restricted_horizon_artist,
    require_horizon_project_access,
    require_horizon_tracker_view_access,
)
from app.services.media import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from app.services.project_access import require_project_auth, verify_path_in_project
from app.services.project_links import linked_virtual_paths_for_source
from app.services.projects import get_project_dir, load_project_links, resolve_horizon_project_root, resolve_project_root_by_id
from app.services.share_access import resolve_shared_horizons_object_target, resolve_shared_media_target, validate_share
from app.services.upload_payloads import require_valid_image_path
from app.services.uploads import ensure_upload_capacity

settings = get_settings()

COMMENT_SHARE_TYPES = ('file', 'folder', 'project-file', 'project-folder', 'project', 'tracker', 'page')
VOICE_NOTE_MAX_DURATION_SECONDS = 300
VOICE_NOTE_MAX_PEAKS = 128
VOICE_NOTE_TRANSCRIPTION_MAX_CHARS = 20000


@dataclass(frozen=True)
class CommentTargetIdentity:
    path: str
    project_id: str | None = None
    horizons_media_asset_id: str | None = None
    horizons_shot_version_id: str | None = None

    @property
    def is_horizons_object(self) -> bool:
        return bool(self.horizons_media_asset_id or self.horizons_shot_version_id)


@dataclass(frozen=True)
class CommentTargetRefs:
    horizons_media_asset_id: str | None = None
    horizons_shot_version_id: str | None = None


def comment_attachment_bucket(path: str) -> str:
    base = (path or 'unknown').encode('utf-8', errors='ignore')
    # This preserves legacy attachment locations; it is a path label, not a
    # signature or credential hash.
    return hashlib.sha1(base, usedforsecurity=False).hexdigest()[:12]


def sanitize_attachment_name(filename: str) -> str:
    safe_name = ''.join(c for c in (filename or '') if c.isalnum() or c in '._- ').strip()
    if not safe_name:
        safe_name = f'attachment_{int(time.time())}.bin'
    return safe_name


def attachment_kind_from_name(filename: str, content_type: str | None = None) -> str:
    if str(content_type or '').lower().startswith('audio/'):
        return 'audio'
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    if ext in VIDEO_EXTENSIONS:
        return 'video'
    if ext in AUDIO_EXTENSIONS:
        return 'audio'
    return ''


def normalize_voice_note_metadata(voice_note: str | None, files: list[UploadFile]) -> dict | None:
    if not voice_note:
        return None
    if len(voice_note) > 50000:
        raise HTTPException(status_code=413, detail='Voice note metadata is too large')
    try:
        raw = json.loads(voice_note)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Invalid voice note metadata')
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail='Invalid voice note metadata')

    filename = sanitize_attachment_name(str(raw.get('filename') or ''))
    matches = [
        upload for upload in files
        if hasattr(upload, 'filename')
        and sanitize_attachment_name(upload.filename or '') == filename
        and attachment_kind_from_name(upload.filename or '', getattr(upload, 'content_type', None)) == 'audio'
    ]
    if len(matches) != 1:
        raise HTTPException(status_code=400, detail='Voice note must reference exactly one uploaded audio file')

    transcription = raw.get('transcription')
    if transcription is not None and not isinstance(transcription, str):
        raise HTTPException(status_code=400, detail='Voice note transcription must be text')
    normalized_transcription = (transcription or '').strip()[:VOICE_NOTE_TRANSCRIPTION_MAX_CHARS] or None

    duration = raw.get('duration')
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(float(duration)):
        raise HTTPException(status_code=400, detail='Voice note duration is invalid')
    normalized_duration = float(duration)
    if normalized_duration <= 0 or normalized_duration > VOICE_NOTE_MAX_DURATION_SECONDS:
        raise HTTPException(status_code=400, detail='Voice note duration must be between 0 and 300 seconds')

    peaks = raw.get('peaks')
    if not isinstance(peaks, list) or not peaks or len(peaks) > VOICE_NOTE_MAX_PEAKS:
        raise HTTPException(status_code=400, detail='Voice note peaks are invalid')
    normalized_peaks = []
    for peak in peaks:
        if isinstance(peak, bool) or not isinstance(peak, (int, float)) or not math.isfinite(float(peak)):
            raise HTTPException(status_code=400, detail='Voice note peaks are invalid')
        normalized_peaks.append(round(min(1.0, max(0.0, float(peak))), 4))

    return {
        'filename': filename,
        'transcription': normalized_transcription,
        'duration': round(normalized_duration, 3),
        'peaks': normalized_peaks,
    }


def _normalize_comment_path(path: str) -> str:
    return (path or '').strip().strip('/')


def _is_horizons_project(db: Session, project_id: str | None) -> bool:
    if not project_id:
        return False
    return db.query(HorizonProject.id).filter(HorizonProject.id == project_id).first() is not None


def _load_horizon_media_asset(db: Session, project_id: str, media_asset_id: str) -> MediaAsset:
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == media_asset_id)
        .filter(MediaAsset.project_id == project_id)
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail='Horizons media asset not found')
    return asset


def _load_horizon_shot_version(db: Session, project_id: str, shot_version_id: str) -> HorizonShotVersion:
    version = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.id == shot_version_id)
        .filter(HorizonShotVersion.project_id == project_id)
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail='Horizons shot version not found')
    return version


def _asset_matches_comment_path(asset: MediaAsset, project_id: str | None, path: str) -> bool:
    normalized_path = _normalize_comment_path(path)
    asset_path = _normalize_comment_path(asset.file_path)
    if not project_id or asset.storage_scope != 'media_root':
        return asset_path == normalized_path
    virtual_paths = linked_virtual_paths_for_source(load_project_links(project_id).get('links', []), asset.file_path)
    return normalized_path in virtual_paths


def _resolve_horizon_comment_target_from_refs(
    db: Session,
    *,
    project_id: str,
    path: str,
    refs: CommentTargetRefs,
) -> CommentTargetIdentity | None:
    normalized_path = _normalize_comment_path(path)
    if not refs.horizons_shot_version_id and not refs.horizons_media_asset_id:
        return None

    asset: MediaAsset | None = None
    version: HorizonShotVersion | None = None

    if refs.horizons_shot_version_id:
        version = _load_horizon_shot_version(db, project_id, refs.horizons_shot_version_id)
        if version.media_asset_id:
            asset = _load_horizon_media_asset(db, project_id, version.media_asset_id)
        elif refs.horizons_media_asset_id:
            raise HTTPException(status_code=409, detail='Shot version is not linked to a media asset')

    if refs.horizons_media_asset_id:
        explicit_asset = _load_horizon_media_asset(db, project_id, refs.horizons_media_asset_id)
        if asset and explicit_asset.id != asset.id:
            raise HTTPException(status_code=409, detail='Comment target refs do not agree on the same horizons object')
        asset = explicit_asset

    canonical_path = _normalize_comment_path(asset.file_path if asset else normalized_path)
    return CommentTargetIdentity(
        path=canonical_path,
        project_id=project_id,
        horizons_media_asset_id=asset.id if asset else refs.horizons_media_asset_id,
        horizons_shot_version_id=version.id if version else None,
    )


def _resolve_horizon_comment_target_from_path(db: Session, *, project_id: str, path: str) -> CommentTargetIdentity:
    normalized_path = _normalize_comment_path(path)
    target = CommentTargetIdentity(path=normalized_path, project_id=project_id)
    if not normalized_path:
        return target

    asset = get_horizon_media_asset_by_path(db, project_id, normalized_path)
    if asset is None:
        return target

    version_ids = [
        version_id
        for version_id, in (
            db.query(HorizonShotVersion.id)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.media_asset_id == asset.id)
            .order_by(HorizonShotVersion.updated_at.desc(), HorizonShotVersion.created_at.desc(), HorizonShotVersion.id.asc())
            .all()
        )
    ]
    version_id = version_ids[0] if len(version_ids) == 1 else None
    return CommentTargetIdentity(
        path=normalized_path,
        project_id=project_id,
        horizons_media_asset_id=asset.id,
        horizons_shot_version_id=version_id,
    )


def resolve_comment_target_identity(
    db: Session,
    *,
    path: str,
    project_id: str | None,
    horizons_media_asset_id: str | None = None,
    horizons_shot_version_id: str | None = None,
) -> CommentTargetIdentity:
    normalized_path = _normalize_comment_path(path)
    target = CommentTargetIdentity(path=normalized_path, project_id=project_id)
    if not normalized_path:
        return target

    if horizons_media_asset_id and not horizons_shot_version_id:
        asset = db.query(MediaAsset).filter(MediaAsset.id == horizons_media_asset_id).first()
        if asset is None:
            raise HTTPException(status_code=404, detail='Media asset not found')
        if project_id and asset.project_id != project_id:
            raise HTTPException(status_code=404, detail='Media asset not found')
        if not project_id and asset.project_id != '__media_root__':
            raise HTTPException(status_code=404, detail='Media asset not found')
        if not _asset_matches_comment_path(asset, project_id, normalized_path):
            raise HTTPException(status_code=409, detail='Media asset does not match comment path')
        return CommentTargetIdentity(
            path=normalized_path,
            project_id=project_id,
            horizons_media_asset_id=asset.id,
        )

    if not _is_horizons_project(db, project_id):
        return target

    refs = CommentTargetRefs(
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )
    explicit_target = _resolve_horizon_comment_target_from_refs(db, project_id=project_id, path=normalized_path, refs=refs)
    if explicit_target is not None:
        return explicit_target

    path_target = _resolve_horizon_comment_target_from_path(db, project_id=project_id, path=normalized_path)
    if path_target.is_horizons_object:
        raise HTTPException(status_code=409, detail='Horizons comment targets require explicit object refs')
    return path_target


def build_comment_record_fields(target: CommentTargetIdentity) -> dict:
    return {
        'file_path': target.path,
        'project_id': target.project_id,
        'horizons_media_asset_id': target.horizons_media_asset_id,
        'horizons_shot_version_id': target.horizons_shot_version_id,
    }


def resolve_comment_canonical_path(comment: Comment, db: Session) -> str:
    if comment.horizons_shot_version_id:
        version = (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.id == comment.horizons_shot_version_id)
            .first()
        )
        if version and version.media_asset_id:
            asset = db.query(MediaAsset).filter(MediaAsset.id == version.media_asset_id).first()
            if asset and (not comment.project_id or asset.project_id == comment.project_id):
                return asset.file_path

    if comment.horizons_media_asset_id:
        asset = db.query(MediaAsset).filter(MediaAsset.id == comment.horizons_media_asset_id).first()
        if asset and (not comment.project_id or asset.project_id == comment.project_id):
            return asset.file_path

    return comment.file_path


def require_comment_access(
    path: str,
    share_id: str | None,
    share_token: str | None,
    vueio_session: str | None,
    db: Session,
    get_user_from_session_fn,
    project_id: str | None = None,
    horizons_media_asset_id: str | None = None,
    horizons_shot_version_id: str | None = None,
):
    normalized_path = _normalize_comment_path(path)
    user = get_user_from_session_fn(vueio_session)
    share = None
    effective_project_id = project_id
    if share_id:
        share = validate_share(share_id, None, db, COMMENT_SHARE_TYPES, share_token=share_token, track_access=False)
        if share.project_id and (horizons_media_asset_id or horizons_shot_version_id):
            resolve_shared_horizons_object_target(
                share,
                db,
                horizons_media_asset_id=horizons_media_asset_id,
                horizons_shot_version_id=horizons_shot_version_id,
            )
        else:
            resolve_shared_media_target(share, normalized_path, db=db)
        effective_project_id = share.project_id or effective_project_id
    elif effective_project_id:
        if _is_horizons_project(db, effective_project_id):
            if not user:
                raise HTTPException(status_code=401, detail='Authentication required')
            _project, access_role = require_horizon_project_access(db, effective_project_id, user, auth_mode='session', required_role='viewer')
            if horizons_shot_version_id and not can_access_horizon_shot_version_id(
                db,
                effective_project_id,
                horizons_shot_version_id,
                user=user,
                access_role=access_role,
            ):
                raise HTTPException(status_code=404, detail='Horizons shot version not found')
            if horizons_media_asset_id and not can_access_horizon_media_asset_id(
                db,
                effective_project_id,
                horizons_media_asset_id,
                user=user,
                access_role=access_role,
            ):
                raise HTTPException(status_code=404, detail='Horizons media asset not found')
        else:
            user = require_project_auth(effective_project_id, vueio_session)
    else:
        if not user:
            raise HTTPException(status_code=401, detail='Authentication required')
        require_file_browser_read_access(vueio_session, normalized_path)
    return user, share, effective_project_id


def serialize_comment(comment: Comment, *, include_references: bool = True) -> dict:
    attachments_data = comment.attachments_data
    if attachments_data and not include_references:
        attachments = [
            item for item in load_attachment_list(comment)
            if item.get('attachment_type') != 'reference'
        ]
        attachments_data = json.dumps(attachments) if attachments else None
    return {
        'id': comment.id,
        'project_id': comment.project_id,
        'file_path': comment.file_path,
        'horizons_media_asset_id': comment.horizons_media_asset_id,
        'horizons_shot_version_id': comment.horizons_shot_version_id,
        'parent_comment_id': comment.parent_comment_id,
        'root_comment_id': comment.root_comment_id,
        'user_name': normalize_comment_author_name(comment.user_name),
        'text': comment.text,
        'timestamp': comment.timestamp,
        'resolved': comment.resolved,
        'created_at': comment.created_at,
        'annotation_data': comment.annotation_data,
        'annotation_target': comment.annotation_target,
        'attachments_data': attachments_data,
    }


def serialize_comment_thread(comment: Comment, replies: list[Comment] | None = None, *, include_references: bool = True) -> dict:
    payload = serialize_comment(comment, include_references=include_references)
    payload['replies'] = [serialize_comment(reply, include_references=include_references) for reply in (replies or [])]
    return payload


def serialize_comment_threads(comments: list[Comment], *, include_references: bool = True) -> list[dict]:
    roots: list[Comment] = []
    replies_by_root: dict[int, list[Comment]] = {}
    known_ids = {comment.id for comment in comments}

    for comment in comments:
        root_id = comment.root_comment_id or comment.parent_comment_id
        if root_id and root_id in known_ids and comment.id != root_id:
            replies_by_root.setdefault(root_id, []).append(comment)
            continue
        roots.append(comment)

    roots.sort(key=lambda comment: (comment.timestamp or 0, comment.created_at or 0, comment.id))
    for replies in replies_by_root.values():
        replies.sort(key=lambda comment: (comment.created_at or 0, comment.id))

    return [
        serialize_comment_thread(comment, replies_by_root.get(comment.id, []), include_references=include_references)
        for comment in roots
    ]


def normalize_comment_author_name(user_name: str | None, user: dict | None = None) -> str:
    if user:
        return (
            user.get('display_name')
            or user.get('name')
            or user.get('username')
            or user.get('id')
            or 'Unknown'
        )

    value = str(user_name or '').strip()
    if not value:
        return 'Shared reviewer'
    if '\n' in value or (len(value) > 48 and ' ' in value):
        return 'Shared reviewer'
    return value


def serialize_comment_write_response(comment: Comment) -> dict:
    payload = serialize_comment(comment)
    payload.pop('resolved', None)
    return payload


def resolve_comment_reply_root(db: Session, *, parent_comment_id: int | None, target: CommentTargetIdentity) -> Comment | None:
    if not parent_comment_id:
        return None

    parent = db.query(Comment).filter(Comment.id == parent_comment_id).first()
    if parent is None:
        raise HTTPException(status_code=404, detail='Parent comment not found')

    root_id = parent.root_comment_id or parent.parent_comment_id or parent.id
    root = parent if parent.id == root_id else db.query(Comment).filter(Comment.id == root_id).first()
    if root is None:
        raise HTTPException(status_code=404, detail='Root comment not found')
    if root.parent_comment_id or root.root_comment_id:
        raise HTTPException(status_code=409, detail='Invalid reply thread root')
    if not comment_matches_target(root, target):
        raise HTTPException(status_code=400, detail='Reply target does not match comment target')
    return root


def load_attachment_list(comment: Comment) -> list[dict]:
    try:
        return json.loads(comment.attachments_data or '[]')
    except Exception:
        return []


def resolve_attachment_target(comment: Comment, attachment_id: str) -> tuple[Path, str]:
    attachments = load_attachment_list(comment)
    attachment = next((item for item in attachments if item.get('id') == attachment_id), None)
    if not attachment:
        raise HTTPException(status_code=404, detail='Attachment not found')
    if attachment.get('attachment_type') == 'reference':
        raise HTTPException(status_code=404, detail='Attachment not found')

    rel_path = attachment.get('rel_path')
    scope = attachment.get('scope')
    if not rel_path:
        raise HTTPException(status_code=404, detail='Attachment missing path')

    if scope == 'project':
        project_id = attachment.get('project_id') or comment.project_id
        if not project_id:
            raise HTTPException(status_code=404, detail='Attachment missing project')
        project_dir = resolve_project_root_by_id(project_id)
        full_path = project_dir / rel_path
        verify_path_in_project(full_path, project_dir)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail='File not found')
        return full_path, f'project:{project_id}:{rel_path}'

    full_path = settings.comment_attachments_dir / rel_path
    try:
        full_path.resolve().relative_to(settings.comment_attachments_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail='Access denied')
    if not full_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return full_path, f'comment:{comment.id}:{attachment_id}'


def delete_comment_attachments(comment: Comment) -> None:
    attachments = load_attachment_list(comment)
    for attachment in attachments:
        if attachment.get('attachment_type') == 'reference':
            continue
        rel_path = attachment.get('rel_path')
        scope = attachment.get('scope')
        if not rel_path:
            continue
        try:
            if scope == 'project':
                project_id = attachment.get('project_id') or comment.project_id
                if not project_id:
                    continue
                project_dir = resolve_project_root_by_id(project_id)
                full_path = project_dir / rel_path
                verify_path_in_project(full_path, project_dir)
            else:
                full_path = settings.comment_attachments_dir / rel_path
                full_path.resolve().relative_to(settings.comment_attachments_dir.resolve())
            if full_path.exists():
                full_path.unlink()
        except Exception:
            continue


def _attachment_kind_from_asset(asset: MediaAsset) -> str:
    ext = Path(asset.file_path or '').suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    if ext in VIDEO_EXTENSIONS:
        return 'video'
    if ext == '.pdf':
        return 'pdf'
    return 'file'


def _build_reference_attachments(
    references: list[dict],
    *,
    project_id: str | None,
    user: dict | None,
    db: Session,
) -> list[dict]:
    if not references:
        return []
    if not project_id or not user or not _is_horizons_project(db, project_id):
        raise HTTPException(status_code=400, detail='Project references are unavailable for this comment')

    _project, access_role = require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode='session',
        required_role='viewer',
    )
    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in references:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail='Invalid project attachment')
        target_type = str(raw.get('target_type') or '').strip()
        target_id = str(raw.get('target_id') or '').strip()
        key = (target_type, target_id)
        if not target_id or target_type not in {'media_asset', 'tracker', 'page'}:
            raise HTTPException(status_code=400, detail='Invalid project attachment')
        if key in seen:
            continue
        seen.add(key)

        if target_type == 'media_asset':
            asset = (
                db.query(MediaAsset)
                .filter(MediaAsset.id == target_id)
                .filter(MediaAsset.project_id == project_id)
                .filter(MediaAsset.unavailable_at.is_(None))
                .first()
            )
            if not asset or not can_access_horizon_media_asset_id(
                db,
                project_id,
                asset.id,
                user=user,
                access_role=access_role,
            ):
                raise HTTPException(status_code=404, detail='Project attachment not found')
            normalized.append({
                'id': uuid.uuid4().hex[:8],
                'attachment_type': 'reference',
                'target_type': 'media_asset',
                'target_id': asset.id,
                'name': Path(asset.file_path).name,
                'kind': _attachment_kind_from_asset(asset),
            })
            continue

        if target_type == 'tracker':
            tracker = require_horizon_tracker_view_access(
                db,
                project_id,
                target_id,
                user=user,
                access_role=access_role,
            )
            normalized.append({
                'id': uuid.uuid4().hex[:8],
                'attachment_type': 'reference',
                'target_type': 'tracker',
                'target_id': tracker.id,
                'name': tracker.name,
                'kind': 'tracker',
            })
            continue

        if is_restricted_horizon_artist(user, access_role):
            raise HTTPException(status_code=404, detail='Project attachment not found')
        page = (
            db.query(HorizonPage)
            .filter(HorizonPage.id == target_id)
            .filter(HorizonPage.project_id == project_id)
            .first()
        )
        if not page:
            raise HTTPException(status_code=404, detail='Project attachment not found')
        normalized.append({
            'id': uuid.uuid4().hex[:8],
            'attachment_type': 'reference',
            'target_type': 'page',
            'target_id': page.id,
            'name': page.title,
            'kind': 'page',
        })
    return normalized


def attach_uploaded_files(comment: Comment, *, path: str, project_id: Optional[str], tracker_name: Optional[str], shot_id: Optional[str], files: list[UploadFile], references: list[dict] | None = None, voice_note: dict | None = None, user: dict | None = None, db: Session) -> Comment:
    incoming_files = [f for f in files if hasattr(f, 'filename') and f.filename and hasattr(f, 'read')]
    attachments = []
    saved_paths: list[Path] = []
    try:
        attachments = _build_reference_attachments(references or [], project_id=project_id, user=user, db=db)
        if len(incoming_files) + len(attachments) > 3:
            raise HTTPException(status_code=400, detail='Max 3 attachments allowed')
        if incoming_files:
            # Uploaded comment binaries are application data, not source media.
            # Keeping one canonical store also lets comments work when project
            # media is intentionally mounted read-only.
            scope = 'app'
            bucket = comment_attachment_bucket(
                f'{project_id or "global"}/{path}'
            )
            rel_root = f'{bucket}/{comment.id}'
            base_dir = settings.comment_attachments_dir / rel_root

            base_dir.mkdir(parents=True, exist_ok=True)
            max_file_bytes = max(0, int(settings.COMMENT_ATTACHMENT_MAX_FILE_BYTES or 0))
            max_total_bytes = max(0, int(settings.COMMENT_ATTACHMENT_MAX_TOTAL_BYTES or 0))
            total_bytes_written = 0
            for upload in incoming_files:
                safe_name = sanitize_attachment_name(upload.filename)
                kind = attachment_kind_from_name(safe_name, upload.content_type)
                if not kind:
                    raise HTTPException(status_code=400, detail='Only image, video, or audio attachments are allowed')
                attachment_id = uuid.uuid4().hex[:8]
                target_file = base_dir / f'{attachment_id}_{safe_name}'
                counter = 1
                while target_file.exists():
                    target_file = base_dir / f'{attachment_id}_{counter}_{safe_name}'
                    counter += 1
                temp_path = target_file.with_suffix(target_file.suffix + '.tmp')
                bytes_written = 0
                try:
                    with open(temp_path, 'wb') as handle:
                        while True:
                            chunk = upload.file.read(1024 * 1024)
                            if not chunk:
                                break
                            if max_file_bytes and bytes_written + len(chunk) > max_file_bytes:
                                raise HTTPException(status_code=413, detail='Comment attachment exceeds the configured file limit')
                            if max_total_bytes and total_bytes_written + bytes_written + len(chunk) > max_total_bytes:
                                raise HTTPException(status_code=413, detail='Comment attachments exceed the configured total limit')
                            ensure_upload_capacity(base_dir, len(chunk))
                            handle.write(chunk)
                            bytes_written += len(chunk)
                    if kind == 'image':
                        require_valid_image_path(
                            temp_path,
                            detail='Comment attachment must be a valid, reasonably sized image',
                        )
                    os.replace(temp_path, target_file)
                except HTTPException:
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                    raise
                except Exception as exc:
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                    raise HTTPException(status_code=500, detail='Upload failed') from exc
                total_bytes_written += bytes_written
                saved_paths.append(target_file)
                attachment = {
                    'id': attachment_id,
                    'attachment_type': 'upload',
                    'name': safe_name,
                    'rel_path': f'{rel_root}/{target_file.name}',
                    'size': bytes_written,
                    'mime': upload.content_type or f'{kind}/*',
                    'kind': kind,
                    'scope': scope,
                    'project_id': project_id if scope == 'project' else None,
                }
                if voice_note and kind == 'audio' and safe_name == voice_note.get('filename'):
                    attachment.update({
                        'transcription': voice_note.get('transcription'),
                        'transcription_status': (
                            'complete'
                            if voice_note.get('transcription')
                            else 'queued'
                            if settings.VOICE_TRANSCRIPTION_ENABLED
                            else 'unavailable'
                        ),
                        'duration': voice_note.get('duration'),
                        'peaks': voice_note.get('peaks'),
                    })
                attachments.append(attachment)

        if attachments:
            comment.attachments_data = json.dumps(attachments)
            db.add(comment)
            db.commit()
            db.refresh(comment)
        return comment
    except Exception:
        for saved in saved_paths:
            try:
                if saved.exists():
                    saved.unlink()
            except Exception:
                pass
        db.delete(comment)
        db.commit()
        raise


def comment_scope_filter(query, *, project_id: str | None):
    if project_id:
        return query.filter(or_(Comment.project_id == project_id, Comment.project_id.is_(None)))
    return query.filter(Comment.project_id.is_(None))


def build_comment_target_filter(target: CommentTargetIdentity):
    if target.horizons_shot_version_id:
        return Comment.horizons_shot_version_id == target.horizons_shot_version_id
    if target.horizons_media_asset_id:
        return and_(
            Comment.horizons_media_asset_id == target.horizons_media_asset_id,
            Comment.horizons_shot_version_id.is_(None),
        )
    return Comment.file_path == target.path


def comment_matches_target(comment: Comment, target: CommentTargetIdentity) -> bool:
    if target.horizons_shot_version_id:
        return comment.horizons_shot_version_id == target.horizons_shot_version_id
    if target.horizons_media_asset_id:
        return comment.horizons_media_asset_id == target.horizons_media_asset_id and comment.horizons_shot_version_id is None
    return comment.file_path == target.path


def backfill_horizons_comment_targets(comments: list[Comment], target: CommentTargetIdentity, db: Session) -> None:
    if not target.is_horizons_object or not target.project_id:
        return

    changed = False
    for comment in comments:
        if comment.project_id != target.project_id:
            continue
        if comment.horizons_media_asset_id == target.horizons_media_asset_id and comment.horizons_shot_version_id == target.horizons_shot_version_id and comment.file_path == target.path:
            continue
        if comment.horizons_media_asset_id or comment.horizons_shot_version_id:
            continue
        if comment.file_path != target.path:
            continue
        comment.horizons_media_asset_id = target.horizons_media_asset_id
        comment.horizons_shot_version_id = target.horizons_shot_version_id
        changed = True

    if changed:
        db.commit()


def resolve_comment_targets(
    target_inputs: list[dict],
    db: Session,
    *,
    project_id: str | None = None,
) -> list[CommentTargetIdentity]:
    targets: list[CommentTargetIdentity] = []
    for target_input in target_inputs:
        path = _normalize_comment_path(target_input.get('path'))
        if not path:
            continue
        refs = target_input.get('refs') or CommentTargetRefs()
        targets.append(
            resolve_comment_target_identity(
                db,
                path=path,
                project_id=project_id,
                horizons_media_asset_id=refs.horizons_media_asset_id,
                horizons_shot_version_id=refs.horizons_shot_version_id,
            )
        )
    return targets


def load_comments_for_targets(
    target_inputs: list[dict],
    db: Session,
    *,
    project_id: str | None = None,
) -> list[list[Comment]]:
    targets = resolve_comment_targets(target_inputs, db, project_id=project_id)
    if not targets:
        return []

    query = comment_scope_filter(db.query(Comment), project_id=project_id)
    rows = query.filter(or_(*[build_comment_target_filter(target) for target in targets])).order_by(Comment.created_at.asc(), Comment.id.asc()).all()

    grouped: list[list[Comment]] = [[] for _ in targets]
    grouped_ids: list[set[int]] = [set() for _ in targets]
    for comment in rows:
        for index, target in enumerate(targets):
            if not comment_matches_target(comment, target):
                continue
            if comment.id in grouped_ids[index]:
                continue
            grouped[index].append(comment)
            grouped_ids[index].add(comment.id)

    for index, target in enumerate(targets):
        backfill_horizons_comment_targets(grouped[index], target, db)

    return grouped


def load_comments_for_paths(
    path_list: list[str],
    db: Session,
    project_id: str | None = None,
    target_refs_by_path: dict[str, CommentTargetRefs] | None = None,
) -> dict[str, list[Comment]]:
    normalized_paths = [_normalize_comment_path(path) for path in path_list if _normalize_comment_path(path)]
    if not normalized_paths:
        return {}

    refs_by_path = target_refs_by_path or {}
    target_inputs = [
        {
            'path': path,
            'refs': refs_by_path.get(path) or CommentTargetRefs(),
        }
        for path in normalized_paths
    ]
    grouped_lists = load_comments_for_targets(target_inputs, db, project_id=project_id)

    grouped: dict[str, list[Comment]] = {path: [] for path in normalized_paths}
    grouped_ids: dict[str, set[int]] = {path: set() for path in normalized_paths}
    for index, path in enumerate(normalized_paths):
        for comment in grouped_lists[index]:
            if comment.id in grouped_ids[path]:
                continue
            grouped[path].append(comment)
            grouped_ids[path].add(comment.id)
    return grouped


def get_comment_counts(
    path_list: list[str],
    db: Session,
    project_id: str | None = None,
    target_refs_by_path: dict[str, CommentTargetRefs] | None = None,
) -> dict:
    grouped = load_comments_for_paths(path_list, db, project_id=project_id, target_refs_by_path=target_refs_by_path)
    counts = {path: len(grouped.get(_normalize_comment_path(path), [])) for path in path_list}
    return counts
