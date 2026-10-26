from __future__ import annotations

import json
import time
from typing import List, Optional

from fastapi import APIRouter, Cookie, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, defer

from app.db import get_db
from app.services.annotation_shapes import AnnotationShape, render_annotation_shapes
from app.services.model_annotations import MAX_ANNOTATION_TARGET_LENGTH, validate_annotation_target
from app.config import get_settings
from app.limiter import enforce_rate_limit
from app.models import Comment
from app.services.auth import get_request_agent_identity, get_request_user, get_user_from_session
from app.services.media import is_image, is_video
from app.services.user_access import is_admin_user
from app.services.comment_visuals import (
    build_comment_visual_context,
    can_generate_comment_frame,
    comment_visual_url,
    frame_timestamp,
    generate_annotated_comment_frame,
    generate_comment_frame,
    media_display_size,
    resolve_project_media,
    write_annotation_png,
)
from app.services.comments import (
    COMMENT_SHARE_TYPES,
    CommentTargetIdentity,
    CommentTargetRefs,
    attach_uploaded_files,
    build_comment_record_fields,
    build_comment_target_filter,
    comment_scope_filter,
    can_delete_any_comment,
    comment_author_id,
    default_comment_path,
    is_comment_author,
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
    serialize_comment,
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
    path: str = Field('', max_length=4096, description='The media file path. Optional when horizons_shot_version_id or horizons_media_asset_id is given.')
    project_id: Optional[str] = None
    horizons_media_asset_id: Optional[str] = None
    horizons_shot_version_id: Optional[str] = Field(None, description='The shot version to comment on.')
    user_name: str = Field('', max_length=120, description='Ignored for signed-in people, who comment under their own name.')
    text: str = Field(max_length=20000)
    timestamp: float = Field(0, description='Seconds into the video where the comment applies. 0 for images.')
    frame: Optional[int] = Field(
        None,
        ge=0,
        description='Frame number where the comment applies, from 0. Use it instead of timestamp. '
        'The server converts it with the frame rate of the video. Needs a shot version or project media file.',
    )
    annotation_data: Optional[str] = Field(None, description='A drawing made in the review player, as a PNG data URL. Agents send annotation_shapes.')
    annotation_shapes: Optional[List[AnnotationShape]] = Field(
        None,
        min_length=1,
        max_length=50,
        description='Marks to draw on the frame at the comment time, such as an arrow to a problem or a box around it. '
        'The server draws them, and people see them in the review player as a drawing. Videos and images of a shot '
        'version or project media file only. Use annotation_data or annotation_shapes, not both. '
        'Check the result with get_comment_annotated_frame.',
    )
    annotation_target: Optional[str] = Field(default=None, max_length=MAX_ANNOTATION_TARGET_LENGTH)
    parent_comment_id: Optional[int] = None

    @model_validator(mode='after')
    def _one_time_and_one_drawing(self):
        if self.frame is not None and 'timestamp' in self.model_fields_set:
            raise ValueError('Send timestamp or frame, not both.')
        if self.annotation_shapes and self.annotation_data:
            raise ValueError('Send annotation_data or annotation_shapes, not both.')
        return self


class CommentUpdate(BaseModel):
    text: str = Field(max_length=20000, description='The new text. It replaces all of the old text.')


class CommentBatchTarget(BaseModel):
    path: str = Field(max_length=4096, description='The media file path. A target with an empty path is skipped.')
    horizons_media_asset_id: Optional[str] = Field(default=None, max_length=128)
    horizons_shot_version_id: Optional[str] = Field(default=None, max_length=128)


class CommentBatchRequest(BaseModel):
    targets: List[CommentBatchTarget] = Field(max_length=250)
    project_id: Optional[str] = Field(default=None, max_length=128)


def _visual_context(comment_id: int, vueio_session: str | None, agent_key: str | None, db: Session) -> dict:
    user, auth_mode = get_request_user(vueio_session, agent_key)
    return build_comment_visual_context(db, comment_id, user, auth_mode)


@router.get('/api/comments/{comment_id}/visual-context', summary='Get comment visual context')
def get_comment_visual_context(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Get the shot, version and image links for one comment on project media.

    Returns the shot code, version label, media asset id and timestamp. It also
    gives URLs of the frame, the drawing and the frame with the drawing.
    `frame_available` is false when the server cannot make a frame.
    """
    ctx =_visual_context(comment_id, vueio_session, x_vueio_agent_key, db)
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
        'frame_unavailable_reason': None if frame_available else 'Open this note in the review player; a server-rendered frame is unavailable.',
        'annotation_url': comment_visual_url(comment.id, 'annotation.png') if comment.annotation_data else None,
        'frame_url': comment_visual_url(comment.id, 'frame.jpg'),
        'annotated_frame_url': comment_visual_url(comment.id, 'annotated-frame.jpg') if comment.annotation_data else comment_visual_url(comment.id, 'frame.jpg'),
        'requires_authentication': True,
    }


@router.get('/api/comments/{comment_id}/annotation.png', summary='Get a comment drawing')
def get_comment_annotation_png(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return the drawing of a comment as a transparent PNG image.

    Returns 404 when the comment has no drawing.
    """
    output =write_annotation_png(_visual_context(comment_id, vueio_session, x_vueio_agent_key, db)['comment'])
    return FileResponse(output, media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})


@router.get('/api/comments/{comment_id}/frame.jpg', summary='Get the frame of a comment')
def get_comment_frame(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return the media frame at the comment's timestamp as a JPEG image.

    For an image file, returns the image. 3D models have no frame.
    """
    output =generate_comment_frame(_visual_context(comment_id, vueio_session, x_vueio_agent_key, db))
    return FileResponse(output, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})


@router.get('/api/comments/{comment_id}/annotated-frame.jpg', summary='Get a comment frame with its drawing')
def get_comment_annotated_frame(comment_id: int, vueio_session: str | None = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Return the frame at the comment's timestamp with the drawing on top.

    The image is a JPEG. Without a drawing, returns the plain frame.
    """
    ctx =_visual_context(comment_id, vueio_session, x_vueio_agent_key, db)
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


def _target_media_path(db: Session, target: CommentTargetIdentity):
    if not target.project_id or not target.horizons_media_asset_id:
        raise HTTPException(status_code=400, detail='Frame numbers and drawn shapes need a shot version or project media file')
    return resolve_project_media(db, target.project_id, target.horizons_media_asset_id)[1]


def _draw_annotation_shapes(shapes: list[AnnotationShape], media_path) -> str:
    if not is_video(media_path) and not is_image(media_path):
        raise HTTPException(status_code=400, detail='Drawn shapes work on videos and images only')
    annotation_data = render_annotation_shapes(shapes, media_display_size(media_path))
    _validate_annotation(annotation_data)
    return annotation_data


def _require_comment_target_access(comment: Comment, user: dict, vueio_session: str | None, db: Session) -> None:
    require_comment_access(
        resolve_comment_canonical_path(comment, db),
        None,
        None,
        vueio_session,
        db,
        get_user_from_session,
        project_id=comment.project_id,
        horizons_media_asset_id=comment.horizons_media_asset_id,
        horizons_shot_version_id=comment.horizons_shot_version_id,
        known_user=user,
    )


def _require_comment_author(comment: Comment | None, user: dict, vueio_session: str | None, db: Session) -> Comment:
    if comment is None:
        raise HTTPException(status_code=404, detail='Comment not found')
    _require_comment_target_access(comment, user, vueio_session, db)
    if not is_comment_author(comment, user):
        raise HTTPException(status_code=403, detail='Only the author can edit this comment')
    return comment


def _require_comment_delete_access(comment: Comment | None, user: dict, vueio_session: str | None, db: Session) -> Comment:
    if comment is None:
        raise HTTPException(status_code=404, detail='Comment not found')
    if is_admin_user(user):
        return comment
    _require_comment_target_access(comment, user, vueio_session, db)
    if not is_comment_author(comment, user) and not can_delete_any_comment(db, comment.project_id, user):
        raise HTTPException(status_code=403, detail='Only the author, a project owner or an admin can delete this comment')
    return comment


def _locked_comment(db: Session, comment_id: int) -> Comment | None:
    return (
        db.query(Comment)
        .populate_existing()
        .filter(Comment.id == comment_id)
        .with_for_update()
        .first()
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
        include_media_data=False,
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


@router.get('/api/comments', summary='List comments', openapi_extra={'x-mcp-tool': 'comments_list'})
def get_comments(
    path: str = Query('', description='The media file path. Optional when horizons_shot_version_id or horizons_media_asset_id is given.'),
    project_id: str | None = None,
    horizons_media_asset_id: str | None = None,
    horizons_shot_version_id: str | None = None,
    limit: int | None = Query(None, ge=1, le=100, description='Return a page of individual comments, including replies. Agent calls default to 20. Follow next_offset until it is null.'),
    offset: int = Query(0, ge=0),
    resolved: bool | None = Query(None, description='Only threads with this resolved state, including their replies.'),
    include_annotations: bool = Query(False, description='Include drawing data. Usually leave false and fetch annotation_url when needed.'),
    share_id: str = None,
    share_token: str = None,
    vueio_session: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """List comments on one shot version or file.

    With limit, returns comments, offset and next_offset. Each record includes
    its parent and root ids so replies can span pages, in id order. Agent calls
    use this format by default. Without limit, browser calls return complete
    threads in timeline order.
    Use resolved=false for open threads. Drawings are available separately at
    annotation_url; include_annotations adds their inline data.
    """
    path = path or default_comment_path(db, project_id, horizons_media_asset_id=horizons_media_asset_id, horizons_shot_version_id=horizons_shot_version_id)
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
    if limit is not None or get_request_agent_identity() or offset or resolved is not None:
        limit = limit or 20
        target = resolve_comment_target_identity(db, path=path, project_id=effective_project_id,
                                                horizons_media_asset_id=horizons_media_asset_id,
                                                horizons_shot_version_id=horizons_shot_version_id)
        query = comment_scope_filter(db.query(Comment), project_id=effective_project_id).filter(build_comment_target_filter(target))
        if resolved is not None:
            roots = query.filter(Comment.parent_comment_id.is_(None), Comment.resolved == resolved).with_entities(Comment.id)
            query = query.filter(or_(Comment.id.in_(roots), Comment.root_comment_id.in_(roots)))
        if not include_annotations:
            query = query.options(defer(Comment.annotation_data))
        rows = query.add_columns(Comment.annotation_data.isnot(None)).order_by(Comment.id).offset(offset).limit(limit + 1).all()
        page, size = [], 0
        for comment, has_annotation in rows[:limit]:
            payload = serialize_comment(comment, include_references=not bool(share), include_annotations=include_annotations)
            payload.update(has_annotation=has_annotation, annotation_url=comment_visual_url(comment.id, 'annotation.png') if has_annotation else None)
            length = len(json.dumps(payload, ensure_ascii=False))
            if page and size + length > 48_000:
                break
            page.append(payload)
            size += length
        return {'comments': page, 'offset': offset, 'next_offset': offset + len(page) if len(rows) > len(page) else None}
    grouped = load_comments_for_paths(
        [path],
        db,
        project_id=effective_project_id,
        target_refs_by_path={(path or '').strip().strip('/'): target_refs} if target_refs else None,
    )
    comments = grouped.get((path or '').strip().strip('/'), [])
    comments = sorted(comments, key=lambda comment: (comment.timestamp or 0, comment.created_at or 0, comment.id))
    result = serialize_comment_threads(comments, include_references=not bool(share))
    if not include_annotations:
        for root in result:
            for comment in [root, *root.get('replies', [])]:
                comment['has_annotation'] = bool(comment.pop('annotation_data', None))
                comment['annotation_url'] = comment_visual_url(comment['id'], 'annotation.png') if comment['has_annotation'] else None
    return result


@router.post('/api/comments', summary='Post a comment', openapi_extra={'x-mcp-tool': 'comment_post'})
def add_comment(request: Request, data: CommentCreate, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Post a comment or a reply on a shot version or file.

    Give `project_id` and `horizons_shot_version_id` for a shot version. Set
    `parent_comment_id` to reply to a thread; a reply uses the time of its
    thread. Give the moment as `timestamp` in seconds or as `frame`. To point
    at something in the picture, send `annotation_shapes`. Write `@` and a
    shot code to mention a shot. The reply leaves out the drawing and gives
    `has_annotation`.
    """
    _enforce_public_comment_mutation_limit(request, share_id)
    if not data.path.strip():
        data.path = default_comment_path(db, data.project_id, horizons_media_asset_id=data.horizons_media_asset_id, horizons_shot_version_id=data.horizons_shot_version_id)
    _validate_annotation(data.annotation_data)
    validate_annotation_target(data.annotation_target)
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
    if data.frame is not None or data.annotation_shapes:
        # Read the media before the tracker lock: probing and drawing take time.
        media_path = _target_media_path(db, target)
        if data.frame is not None:
            data.timestamp = frame_timestamp(media_path, data.frame)
        if data.annotation_shapes:
            data.annotation_data = _draw_annotation_shapes(data.annotation_shapes, media_path)
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
        author_user_id=comment_author_id(user),
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


@router.post('/api/comments/with-attachments', summary='Post a comment with attachments')
async def add_comment_with_attachments(
    request: Request,
    path: str = Form('', description='The media file path. Optional when horizons_shot_version_id or horizons_media_asset_id is given.'),
    user_name: str = Form('', description='Ignored for signed-in people, who comment under their own name.'),
    text: str = Form(''),
    timestamp: Optional[float] = Form(None, description='Seconds into the video where the comment applies. 0 for images.'),
    frame: Optional[int] = Form(None, ge=0, description='Frame number from 0, instead of timestamp. Needs a shot version or project media file.'),
    annotation_data: Optional[str] = Form(None),
    annotation_target: Optional[str] = Form(None),
    parent_comment_id: Optional[int] = Form(None),
    project_id: Optional[str] = Form(None),
    horizons_media_asset_id: Optional[str] = Form(None),
    horizons_shot_version_id: Optional[str] = Form(None),
    tracker_name: Optional[str] = Form(None),
    shot_id: Optional[str] = Form(None),
    linked_attachments: str = Form('[]'),
    voice_note: Optional[str] = Form(
        None,
        description='JSON {filename, transcription} for an audio file in `files` that is a voice note. Optional: '
        'the server measures the length and waveform of every audio file. Send it to give your own transcription.',
    ),
    files: List[UploadFile] = File(default=[]),
    share_id: str = None,
    share_token: str = None,
    vueio_session: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """Post a comment or reply with uploaded files or project references.

    Other fields work as in comment_post. To draw shapes, use comment_post.
    `files` are images, videos or audio; a comment has up to 3 attachments.
    An audio file becomes a voice note with a waveform and, when the server
    can, a transcription. `linked_attachments` is a JSON list of
    {target_type, target_id}; target_type is media_asset, folder, shot,
    tracker or page. Add `marker`, such as "@SH010", to make an item an inline
    mention. `tracker_name` and `shot_id` are not used.
    """
    _enforce_public_comment_mutation_limit(request, share_id)
    if len(path) > 4096 or len(user_name) > 120 or len(text) > 20000:
        raise HTTPException(status_code=413, detail='Comment fields are too large')
    if frame is not None and timestamp is not None:
        raise HTTPException(status_code=400, detail='Send timestamp or frame, not both')
    if not path.strip():
        path = default_comment_path(db, project_id, horizons_media_asset_id=horizons_media_asset_id, horizons_shot_version_id=horizons_shot_version_id)
    _validate_annotation(annotation_data)
    validate_annotation_target(annotation_target)
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
    if frame is not None:
        timestamp = frame_timestamp(_target_media_path(db, target), frame)
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
        author_user_id=comment_author_id(user),
        text=text,
        timestamp=reply_root.timestamp if reply_root else (timestamp or 0),
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
    for attachment in load_attachment_list(comment):
        if attachment.get('kind') == 'audio' and attachment.get('transcription_status') == 'queued':
            enqueue_voice_note_transcription(comment.id, str(attachment.get('id')))
    return payload


@router.get('/api/comments/{comment_id}/attachments/{attachment_id}', summary='Get a comment attachment')
def stream_comment_attachment(comment_id: int, attachment_id: str, request: Request, download: bool = False, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Return one uploaded attachment file of a comment.

    `attachment_id` is the `id` of an item in the comment's `attachments_data`.
    Set `download` to true to get the file as a download; this is recorded.
    Project references are not files and return 404.
    """
    comment =db.query(Comment).filter(Comment.id == comment_id).first()
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


@router.post('/api/comments/{comment_id}/resolve', summary='Resolve or reopen a comment', openapi_extra={'x-mcp-tool': 'comment_resolve'})
def resolve_comment(
    request: Request,
    comment_id: int,
    resolved: Optional[bool] = Query(None, description='true resolves the thread and false reopens it. Without it, the state flips.'),
    share_id: str = None,
    share_token: str = None,
    vueio_session: str = Cookie(None),
    db: Session = Depends(get_db),
):
    """Mark a comment thread as resolved, or reopen it.

    Returns the new `resolved` state. A change records a comment_resolved
    event.
    """
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
    comment = _locked_comment(db, comment_id)
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
    if resolved is not None and bool(comment.resolved) == resolved:
        return {'resolved': comment.resolved}
    comment.resolved = (not comment.resolved) if resolved is None else resolved
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


@router.put('/api/comments/{comment_id}', summary='Edit a comment')
def update_comment(comment_id: int, data: CommentUpdate, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Change the text of a comment that you wrote.

    Only the author can edit a comment. The time, drawing, attachments and
    mentions do not change. The comment gets `edited_at`, and a
    comment_edited event is recorded.
    """
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    comment = _require_comment_author(db.query(Comment).filter(Comment.id == comment_id).first(), user, vueio_session, db)
    lock_tracker_for_comment_target(
        db,
        project_id=comment.project_id,
        shot_version_id=comment.horizons_shot_version_id,
        media_asset_id=comment.horizons_media_asset_id,
    )
    comment = _require_comment_author(_locked_comment(db, comment_id), user, vueio_session, db)
    if data.text == comment.text:
        return serialize_comment_write_response(comment)
    if not data.text.strip() and not comment.annotation_data and not load_attachment_list(comment):
        raise HTTPException(status_code=400, detail='Comment cannot be empty')
    comment.text = data.text
    comment.edited_at = time.time()
    db.add(comment)
    db.flush()
    actor = build_tracker_event_actor(user=user, source='app')
    record_comment_tracker_event(
        db,
        comment=comment,
        event_type='comment_edited',
        actor_id=actor['actor_id'],
        actor_name=actor['actor_name'],
        source=actor['source'],
        created_at=comment.edited_at,
    )
    db.commit()
    return serialize_comment_write_response(comment)


@router.delete('/api/comments/{comment_id}', summary='Delete a comment')
def delete_comment(comment_id: int, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Delete a comment, with its replies when it starts a thread.

    You can delete the comments that you wrote. Project owners and admins can
    delete any comment in the project; restricted members cannot. Attachment
    files stay on disk, so tracker history can restore a comment on a shot
    version. Records a comment_deleted event.
    """
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    comment = _require_comment_delete_access(db.query(Comment).filter(Comment.id == comment_id).first(), user, vueio_session, db)
    event_context = lock_tracker_for_comment_target(
        db,
        project_id=comment.project_id,
        shot_version_id=comment.horizons_shot_version_id,
        media_asset_id=comment.horizons_media_asset_id,
    ) if comment.project_id else None
    comment = _require_comment_delete_access(_locked_comment(db, comment_id), user, vueio_session, db)
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


@router.post('/api/comments/counts/batch', summary='Count comments on many files')
def get_comment_counts_batch(request: Request, batch: CommentBatchRequest, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Count the comments on many shot versions or files in one call.

    Each target needs a `path`. For a shot version, also give
    `horizons_shot_version_id`. Counts include replies. Targets that you
    cannot see are left out of the result.
    """
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


@router.post('/api/comments/previews/batch', summary='Preview comments on many files')
def get_comment_previews_batch(request: Request, batch: CommentBatchRequest, share_id: str = None, share_token: str = None, vueio_session: str = Cookie(None), db: Session = Depends(get_db)):
    """Get a short text preview of the comments on many files in one call.

    Each preview joins the comment texts, oldest first, up to 280 characters.
    Targets work as in get_comment_counts_batch.
    """
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
