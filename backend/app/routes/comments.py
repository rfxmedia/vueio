from __future__ import annotations

import json
import time
from typing import List, Optional

from fastapi import APIRouter, Cookie, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import get_settings
from app.limiter import enforce_rate_limit
from app.models import Comment
from app.services.auth import get_request_user, get_user_from_session
from app.services.comment_visuals import (
    build_comment_visual_context,
    can_generate_comment_frame,
    comment_visual_url,
    generate_annotated_comment_frame,
    generate_comment_frame,
    write_annotation_png,
)
from app.services.comments import (
    COMMENT_SHARE_TYPES,
    CommentTargetRefs,
    attach_uploaded_files,
    build_comment_record_fields,
    preserve_comment_attachments,
    load_attachment_list,
    load_comments_for_paths,
    normalize_voice_note_metadata,
    load_comments_for_targets,
    normalize_comment_author_name,
    require_comment_access,
    resolve_comment_reply_root,
    resolve_attachment_target,
    resolve_comment_canonical_path,
    resolve_comment_target_identity,
    serialize_comment_threads,
    serialize_comment_write_response,
    validate_comment_reference_limits,
)
from app.services.share_access import validate_share
from app.services.media_serving import DownloadAuditSpec, media_target, serve_download, serve_file
from app.services.tracker_events import build_tracker_event_actor, lock_tracker_for_comment_target, record_comment_tracker_event
from app.services.upload_payloads import validate_png_data_url
from app.services.voice_transcription import enqueue_voice_note_transcription

router = APIRouter(tags=['comments'])
settings = get_settings()


class CommentCreate(BaseModel):
    path: str = Field(max_length=4096)
    project_id: Optional[str] = None
    horizons_media_asset_id: Optional[str] = None
    horizons_shot_version_id: Optional[str] = None
    user_name: str = Field(max_length=120)
    text: str = Field(max_length=20000)
    timestamp: float
    annotation_data: Optional[str] = None
    annotation_target: Optional[str] = Field(default=None, max_length=100)
    parent_comment_id: Optional[int] = None


class CommentBatchTarget(BaseModel):
    path: str = Field(max_length=4096)
    horizons_media_asset_id: Optional[str] = Field(default=None, max_length=128)
    horizons_shot_version_id: Optional[str] = Field(default=None, max_length=128)


class CommentBatchRequest(BaseModel):
    targets: List[CommentBatchTarget] = Field(max_length=250)
    project_id: Optional[str] = Field(default=None, max_length=128)


def _visual_context(comment_id: int, vueio_session: str | None, agent_key: str | None, db: Session) -> dict:
    user, auth_mode = get_request_user(vueio_session, agent_key)
    return build_comment_visual_context(db, comment_id, user, auth_mode)


@router.get('/api/comments/{comment_id}/visual-context')
def get_comment_visual_context(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _visual_context(comment_id, vueio_session, x_vueio_agent_key, db)
    comment, shot, version, asset = ctx['comment'], ctx['shot'], ctx['version'], ctx['asset']
    frame_available = can_generate_comment_frame(ctx['full_path'])
    return {
        'comment_id': comment.id,
        'project_id': comment.project_id,
        'shot_id': shot.id if shot else None,
        'shot_code': shot.shot_code if shot else None,
        'shot_version_id': version.id if version else comment.horizons_shot_version_id,
        'version_label': version.label if version else None,
        'media_asset_id': asset.id,
        'timestamp': comment.timestamp,
        'has_annotation': bool(comment.annotation_data),
        'frame_available': frame_available,
        'frame_unavailable_reason': None if frame_available else 'ffmpeg is not available for video frame extraction',
        'annotation_url': comment_visual_url(comment.id, 'annotation.png') if comment.annotation_data else None,
        'frame_url': comment_visual_url(comment.id, 'frame.jpg'),
        'annotated_frame_url': comment_visual_url(comment.id, 'annotated-frame.jpg') if comment.annotation_data else comment_visual_url(comment.id, 'frame.jpg'),
        'requires_authentication': True,
    }


@router.get('/api/comments/{comment_id}/annotation.png')
def get_comment_annotation_png(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    output = write_annotation_png(_visual_context(comment_id, vueio_session, x_vueio_agent_key, db)['comment'])
    return FileResponse(output, media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})


@router.get('/api/comments/{comment_id}/frame.jpg')
def get_comment_frame(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    output = generate_comment_frame(_visual_context(comment_id, vueio_session, x_vueio_agent_key, db))
    return FileResponse(output, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})


@router.get('/api/comments/{comment_id}/annotated-frame.jpg')
def get_comment_annotated_frame(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    ctx = _visual_context(comment_id, vueio_session, x_vueio_agent_key, db)
    output = generate_annotated_comment_frame(ctx) if ctx['comment'].annotation_data else generate_comment_frame(ctx)
    return FileResponse(output, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})


def _validate_annotation(annotation_data: str | None) -> None:
    validate_png_data_url(
        annotation_data,
        max_bytes=settings.COMMENT_ANNOTATION_MAX_BYTES,
        too_large_detail='Comment annotation is too large',
        invalid_detail='Comment annotation must be a valid PNG image',
    )


def _enforce_public_comment_mutation_limit(request: Request, share_id: str | None) -> None:
    if share_id:
        enforce_rate_limit(
            request,
            settings.PUBLIC_COMMENT_CREATE_RATE_LIMIT,
            scope='public-comment-mutation',
        )


def _build_target_refs(*, horizons_media_asset_id: str | None = None, horizons_shot_version_id: str | None = None) -> CommentTargetRefs | None:
    if not horizons_media_asset_id and not horizons_shot_version_id:
        return None
    return CommentTargetRefs(
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )


def _resolve_list_scope(targets: list[CommentBatchTarget], *, project_id: str | None, share_id: str | None, share_token: str | None, vueio_session: str | None, db: Session):
    user = get_user_from_session(vueio_session)
    share = None
    effective_project_id = project_id
    allowed_targets = list(targets)
    if share_id:
        share = validate_share(share_id, None, db, COMMENT_SHARE_TYPES, share_token=share_token, track_access=False)
        effective_project_id = share.project_id or effective_project_id
    elif effective_project_id:
        first = targets[0] if targets else None
        require_comment_access(
            first.path if first else '',
            None,
            None,
            vueio_session,
            db,
            get_user_from_session,
            project_id=effective_project_id,
            horizons_media_asset_id=first.horizons_media_asset_id if first else None,
            horizons_shot_version_id=first.horizons_shot_version_id if first else None,
        )
    elif not user:
        raise HTTPException(status_code=401, detail='Authentication required')

    if share:
        allowed_targets = []
        for target in targets:
            try:
                require_comment_access(
                    target.path,
                    share_id,
                    share_token,
                    vueio_session,
                    db,
                    get_user_from_session,
                    horizons_media_asset_id=target.horizons_media_asset_id,
                    horizons_shot_version_id=target.horizons_shot_version_id,
                )
                allowed_targets.append(target)
            except HTTPException:
                continue
    elif effective_project_id:
        allowed_targets = []
        for target in targets:
            try:
                require_comment_access(
                    target.path,
                    None,
                    None,
                    vueio_session,
                    db,
                    get_user_from_session,
                    project_id=effective_project_id,
                    horizons_media_asset_id=target.horizons_media_asset_id,
                    horizons_shot_version_id=target.horizons_shot_version_id,
                )
                allowed_targets.append(target)
            except HTTPException:
                continue
    else:
        allowed_targets = []
        for target in targets:
            try:
                require_comment_access(target.path, None, None, vueio_session, db, get_user_from_session, project_id=None)
                allowed_targets.append(target)
            except HTTPException:
                continue

    return allowed_targets, effective_project_id


def _comment_target_key(path: str, refs: CommentTargetRefs | None = None) -> str:
    refs = refs or CommentTargetRefs()
    normalized_path = (path or '').strip().strip('/')
    if refs.horizons_shot_version_id:
        return f'version:{refs.horizons_shot_version_id}'
    if refs.horizons_media_asset_id:
        return f'asset:{refs.horizons_media_asset_id}'
    return f'path:{normalized_path}'


def _preview_text_from_comments(comments: list[Comment]) -> str:
    parts: list[str] = []
    for comment in sorted(comments, key=lambda item: (item.created_at or 0, item.id)):
        text_part = str(comment.text or '').strip()
        if text_part:
            parts.append(text_part)
        elif comment.annotation_data:
            parts.append('Drawing annotation')

    if not parts:
        return 'No comments yet.'

    preview = ''
    max_preview_chars = 280
    for part in parts:
        candidate = f'{preview} {part}'.strip() if preview else part
        if len(candidate) > max_preview_chars:
            if not preview:
                preview = part[: max_preview_chars - 1].rstrip() + '…'
            else:
                preview = preview.rstrip() + '…'
            break
        preview = candidate
    return preview or 'No comments yet.'


def _filter_batch_targets(batch: CommentBatchRequest, *, project_id: str | None, share_id: str | None, share_token: str | None, vueio_session: str | None, db: Session):
    normalized_targets = []
    for target in batch.targets:
        path = (target.path or '').strip().strip('/')
        if not path:
            continue
        normalized_targets.append(CommentBatchTarget(
            path=path,
            horizons_media_asset_id=target.horizons_media_asset_id,
            horizons_shot_version_id=target.horizons_shot_version_id,
        ))
    if not normalized_targets:
        return [], project_id

    allowed_targets, effective_project_id = _resolve_list_scope(
        normalized_targets,
        project_id=project_id,
        share_id=share_id,
        share_token=share_token,
        vueio_session=vueio_session,
        db=db,
    )
    if not allowed_targets:
        return [], effective_project_id

    return allowed_targets, effective_project_id


def _build_batch_grouped_comments(targets: list[CommentBatchTarget], *, project_id: str | None, db: Session):
    if not targets:
        return []
    return load_comments_for_targets(
        [
            {
                'path': target.path,
                'refs': _build_target_refs(
                    horizons_media_asset_id=target.horizons_media_asset_id,
                    horizons_shot_version_id=target.horizons_shot_version_id,
                ) or CommentTargetRefs(),
            }
            for target in targets
        ],
        db,
        project_id=project_id,
    )


def _serialize_count_batch_items(targets: list[CommentBatchTarget], grouped_comments: list[list[Comment]]):
    return [
        {
            'path': target.path,
            'horizons_media_asset_id': target.horizons_media_asset_id,
            'horizons_shot_version_id': target.horizons_shot_version_id,
            'key': _comment_target_key(target.path, _build_target_refs(
                horizons_media_asset_id=target.horizons_media_asset_id,
                horizons_shot_version_id=target.horizons_shot_version_id,
            )),
            'count': len(grouped_comments[index]),
        }
        for index, target in enumerate(targets)
    ]


def _serialize_preview_batch_items(targets: list[CommentBatchTarget], grouped_comments: list[list[Comment]]):
    return [
        {
            'path': target.path,
            'horizons_media_asset_id': target.horizons_media_asset_id,
            'horizons_shot_version_id': target.horizons_shot_version_id,
            'key': _comment_target_key(target.path, _build_target_refs(
                horizons_media_asset_id=target.horizons_media_asset_id,
                horizons_shot_version_id=target.horizons_shot_version_id,
            )),
            'preview': _preview_text_from_comments(grouped_comments[index]),
        }
        for index, target in enumerate(targets)
    ]


@router.get('/api/comments')
def get_comments(
    path: str,
    project_id: str | None = None,
    horizons_media_asset_id: str | None = None,
    horizons_shot_version_id: str | None = None,
    share_id: str = None,
    share_token: str = None,
    vueio_session: str = Cookie(None),
    db: Session = Depends(get_db),
):
    _user, share, effective_project_id = require_comment_access(
        path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=project_id,
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )
    if share and share.project_id:
        effective_project_id = share.project_id
    target_refs = _build_target_refs(
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )
    grouped = load_comments_for_paths(
        [path],
        db,
        project_id=effective_project_id,
        target_refs_by_path={(path or '').strip().strip('/'): target_refs} if target_refs else None,
    )
    comments = grouped.get((path or '').strip().strip('/'), [])
    comments = sorted(comments, key=lambda comment: (comment.timestamp or 0, comment.created_at or 0, comment.id))
    return serialize_comment_threads(comments, include_references=not bool(share))


@router.post('/api/comments')
def add_comment(request: Request, data: CommentCreate, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    _enforce_public_comment_mutation_limit(request, share_id)
    _validate_annotation(data.annotation_data)
    user, share, effective_project_id = require_comment_access(
        data.path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=data.project_id,
        horizons_media_asset_id=data.horizons_media_asset_id,
        horizons_shot_version_id=data.horizons_shot_version_id,
    )
    if share and share.project_id:
        effective_project_id = share.project_id
    target = resolve_comment_target_identity(
        db,
        path=data.path,
        project_id=effective_project_id,
        horizons_media_asset_id=data.horizons_media_asset_id,
        horizons_shot_version_id=data.horizons_shot_version_id,
    )
    lock_tracker_for_comment_target(
        db,
        project_id=target.project_id,
        shot_version_id=target.horizons_shot_version_id,
        media_asset_id=target.horizons_media_asset_id,
    )
    user, share, effective_project_id = require_comment_access(
        data.path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=data.project_id,
        horizons_media_asset_id=data.horizons_media_asset_id,
        horizons_shot_version_id=data.horizons_shot_version_id,
        known_user=user,
    )
    if share and share.project_id:
        effective_project_id = share.project_id
    target = resolve_comment_target_identity(
        db,
        path=data.path,
        project_id=effective_project_id,
        horizons_media_asset_id=data.horizons_media_asset_id,
        horizons_shot_version_id=data.horizons_shot_version_id,
    )
    reply_root = resolve_comment_reply_root(db, parent_comment_id=data.parent_comment_id, target=target)
    comment = Comment(
        **build_comment_record_fields(target),
        user_name=normalize_comment_author_name(data.user_name, user),
        text=data.text,
        timestamp=reply_root.timestamp if reply_root else data.timestamp,
        annotation_data=data.annotation_data,
        annotation_target=data.annotation_target,
        parent_comment_id=reply_root.id if reply_root else None,
        root_comment_id=reply_root.id if reply_root else None,
    )
    db.add(comment)
    db.flush()
    actor = build_tracker_event_actor(
        user=user,
        source='share' if share else 'app',
        actor_name=comment.user_name,
    )
    record_comment_tracker_event(
        db,
        comment=comment,
        event_type='comment_added',
        actor_id=actor['actor_id'],
        actor_name=actor['actor_name'],
        source=actor['source'],
    )
    db.commit()
    return serialize_comment_write_response(comment)


@router.post('/api/comments/with-attachments')
async def add_comment_with_attachments(
    request: Request,
    path: str = Form(...),
    user_name: str = Form(...),
    text: str = Form(''),
    timestamp: float = Form(0),
    annotation_data: Optional[str] = Form(None),
    annotation_target: Optional[str] = Form(None),
    parent_comment_id: Optional[int] = Form(None),
    project_id: Optional[str] = Form(None),
    horizons_media_asset_id: Optional[str] = Form(None),
    horizons_shot_version_id: Optional[str] = Form(None),
    tracker_name: Optional[str] = Form(None),
    shot_id: Optional[str] = Form(None),
    linked_attachments: str = Form('[]'),
    voice_note: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    share_id: str = None,
    share_token: str = None,
    vueio_session: str = Cookie(None),
    db: Session = Depends(get_db),
):
    _enforce_public_comment_mutation_limit(request, share_id)
    if len(path) > 4096 or len(user_name) > 120 or len(text) > 20000:
        raise HTTPException(status_code=413, detail='Comment fields are too large')
    _validate_annotation(annotation_data)
    if annotation_target and len(annotation_target) > 100:
        raise HTTPException(status_code=413, detail='Comment annotation target is too large')
    user, share, effective_project_id = require_comment_access(
        path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=project_id,
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )
    if share and share.project_id:
        effective_project_id = share.project_id
    try:
        references = json.loads(linked_attachments or '[]')
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Invalid linked attachments')
    if not isinstance(references, list):
        raise HTTPException(status_code=400, detail='Invalid linked attachments')
    validate_comment_reference_limits(references, file_count=len(files))
    if share and references:
        raise HTTPException(status_code=403, detail='Project references are unavailable on shared links')
    voice_note_metadata = normalize_voice_note_metadata(voice_note, files)
    if not (text or '').strip() and not annotation_data and not files and not references:
        raise HTTPException(status_code=400, detail='Comment cannot be empty')

    target = resolve_comment_target_identity(
        db,
        path=path,
        project_id=effective_project_id,
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )
    lock_tracker_for_comment_target(
        db,
        project_id=target.project_id,
        shot_version_id=target.horizons_shot_version_id,
        media_asset_id=target.horizons_media_asset_id,
    )
    user, share, effective_project_id = require_comment_access(
        path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=project_id,
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
        known_user=user,
    )
    if share and share.project_id:
        effective_project_id = share.project_id
    target = resolve_comment_target_identity(
        db,
        path=path,
        project_id=effective_project_id,
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )
    reply_root = resolve_comment_reply_root(db, parent_comment_id=parent_comment_id, target=target)
    comment = Comment(
        **build_comment_record_fields(target),
        user_name=normalize_comment_author_name(user_name, user),
        text=text,
        timestamp=reply_root.timestamp if reply_root else timestamp,
        annotation_data=annotation_data,
        annotation_target=annotation_target,
        attachments_data=None,
        parent_comment_id=reply_root.id if reply_root else None,
        root_comment_id=reply_root.id if reply_root else None,
    )
    db.add(comment)
    db.flush()

    comment = attach_uploaded_files(
        comment,
        path=path,
        project_id=effective_project_id,
        tracker_name=tracker_name,
        shot_id=shot_id,
        files=files,
        references=references,
        voice_note=voice_note_metadata,
        user=user,
        db=db,
    )
    actor = build_tracker_event_actor(
        user=user,
        source='share' if share else 'app',
        actor_name=comment.user_name,
    )
    record_comment_tracker_event(
        db,
        comment=comment,
        event_type='comment_added',
        actor_id=actor['actor_id'],
        actor_name=actor['actor_name'],
        source=actor['source'],
    )
    db.commit()
    payload = serialize_comment_write_response(comment)
    if voice_note_metadata and not voice_note_metadata.get('transcription'):
        attachment = next((
            item for item in load_attachment_list(comment)
            if item.get('attachment_type') == 'upload'
            and item.get('kind') == 'audio'
            and item.get('name') == voice_note_metadata.get('filename')
        ), None)
        if attachment:
            attachment_id = str(attachment.get('id'))
            enqueue_voice_note_transcription(comment.id, attachment_id)
    return payload


@router.get('/api/comments/{comment_id}/attachments/{attachment_id}')
def stream_comment_attachment(comment_id: int, attachment_id: str, request: Request, download: bool = False, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail='Comment not found')
    access_path = resolve_comment_canonical_path(comment, db)
    _user, share, _effective_project_id = require_comment_access(
        access_path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=comment.project_id,
        horizons_media_asset_id=comment.horizons_media_asset_id,
        horizons_shot_version_id=comment.horizons_shot_version_id,
    )
    if download and share and not share.allow_download:
        raise HTTPException(status_code=403, detail='Downloads are disabled for this share link')
    full_path, transcode_key = resolve_attachment_target(comment, attachment_id)
    attachment = next((item for item in load_attachment_list(comment) if str(item.get('id')) == attachment_id), None)
    if download:
        return serve_download(
            media_target(full_path, transcode_key),
            db,
            request=request,
            audit=DownloadAuditSpec({
                'source': 'share' if share else 'app',
                'share_id': share.id if share else None,
                'project_id': comment.project_id,
                'event_type': 'download_file',
                'resource_type': 'comment_attachment',
                'resource_id': f'{comment.id}:{attachment_id}',
                'resource_name': full_path.name,
                'filename': full_path.name,
                'paths': [access_path],
                'size_bytes': full_path.stat().st_size if full_path.is_file() else None,
                'metadata': {'comment_id': comment.id, 'attachment_id': attachment_id},
            }),
        )
    is_audio = attachment and attachment.get('kind') == 'audio'
    return serve_file(
        media_target(full_path, transcode_key),
        db,
        range_header=request.headers.get('range'),
        enable_ranges=bool(is_audio),
    )


@router.post('/api/comments/{comment_id}/resolve')
def resolve_comment(request: Request, comment_id: int, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    _enforce_public_comment_mutation_limit(request, share_id)
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404)
    access_path = resolve_comment_canonical_path(comment, db)
    user, share, _effective_project_id = require_comment_access(
        access_path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=comment.project_id,
        horizons_media_asset_id=comment.horizons_media_asset_id,
        horizons_shot_version_id=comment.horizons_shot_version_id,
    )
    lock_tracker_for_comment_target(
        db,
        project_id=comment.project_id,
        shot_version_id=comment.horizons_shot_version_id,
        media_asset_id=comment.horizons_media_asset_id,
    )
    comment = (
        db.query(Comment)
        .populate_existing()
        .filter(Comment.id == comment_id)
        .with_for_update()
        .first()
    )
    if comment is None:
        raise HTTPException(status_code=404, detail='Comment not found')
    access_path = resolve_comment_canonical_path(comment, db)
    user, share, _effective_project_id = require_comment_access(
        access_path,
        share_id,
        share_token,
        vueio_session,
        db,
        get_user_from_session,
        project_id=comment.project_id,
        horizons_media_asset_id=comment.horizons_media_asset_id,
        horizons_shot_version_id=comment.horizons_shot_version_id,
        known_user=user,
    )
    comment.resolved = not comment.resolved
    db.add(comment)
    db.flush()
    actor = build_tracker_event_actor(
        user=user,
        source='share' if share else 'app',
        actor_name=comment.user_name if share else None,
    )
    record_comment_tracker_event(
        db,
        comment=comment,
        event_type='comment_resolved',
        actor_id=actor['actor_id'],
        actor_name=actor['actor_name'],
        source=actor['source'],
        created_at=time.time(),
    )
    db.commit()
    return {'resolved': comment.resolved}


@router.delete('/api/comments/{comment_id}')
def delete_comment(comment_id: int, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    user = get_user_from_session(vueio_session)
    if not user or user['role'] != 'admin':
        raise HTTPException(status_code=403, detail='Admin access required')
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail='Comment not found')
    event_context = lock_tracker_for_comment_target(
        db,
        project_id=comment.project_id,
        shot_version_id=comment.horizons_shot_version_id,
        media_asset_id=comment.horizons_media_asset_id,
    ) if comment.project_id else None
    comment = (
        db.query(Comment)
        .populate_existing()
        .filter(Comment.id == comment_id)
        .with_for_update()
        .first()
    )
    if comment is None:
        raise HTTPException(status_code=404, detail='Comment not found')
    deleted_comment_id = comment.id
    deleted_comment_text = comment.text
    comments_to_delete = [comment]
    if not comment.parent_comment_id and not comment.root_comment_id:
        comments_to_delete.extend(
            db.query(Comment)
            .filter(Comment.root_comment_id == comment.id)
            .order_by(Comment.created_at.asc(), Comment.id.asc())
            .all()
        )
    for item in comments_to_delete:
        preserve_comment_attachments(item)
        db.delete(item)
    db.flush()
    if event_context:
        from app.services.tracker_events import create_tracker_event

        actor = build_tracker_event_actor(user=user, source='app')
        create_tracker_event(
            db,
            project_id=comment.project_id,
            tracker_id=event_context['tracker_id'],
            shot_id=event_context['shot_id'],
            shot_version_id=event_context['shot_version_id'],
            comment_id=deleted_comment_id,
            event_type='comment_deleted',
            actor_id=actor['actor_id'],
            actor_name=actor['actor_name'],
            source=actor['source'],
            payload={
                **event_context,
                'body': deleted_comment_text,
                'reply_count': max(0, len(comments_to_delete) - 1),
            },
        )
    db.commit()
    return {'status': 'deleted'}


@router.post('/api/comments/counts/batch')
def get_comment_counts_batch(request: Request, batch: CommentBatchRequest, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    if share_id:
        enforce_rate_limit(
            request,
            settings.PUBLIC_COMMENT_BATCH_RATE_LIMIT,
            scope='public-comment-batch',
        )
    targets, effective_project_id = _filter_batch_targets(
        batch,
        project_id=batch.project_id,
        share_id=share_id,
        share_token=share_token,
        vueio_session=vueio_session,
        db=db,
    )
    if not targets:
        return {'items': []}

    grouped_comments = _build_batch_grouped_comments(targets, project_id=effective_project_id, db=db)
    return {'items': _serialize_count_batch_items(targets, grouped_comments)}


@router.post('/api/comments/previews/batch')
def get_comment_previews_batch(request: Request, batch: CommentBatchRequest, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    if share_id:
        enforce_rate_limit(
            request,
            settings.PUBLIC_COMMENT_BATCH_RATE_LIMIT,
            scope='public-comment-batch',
        )
    targets, effective_project_id = _filter_batch_targets(
        batch,
        project_id=batch.project_id,
        share_id=share_id,
        share_token=share_token,
        vueio_session=vueio_session,
        db=db,
    )
    if not targets:
        return {'items': []}

    grouped_comments = _build_batch_grouped_comments(targets, project_id=effective_project_id, db=db)
    return {'items': _serialize_preview_batch_items(targets, grouped_comments)}
