from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.services.hls_streaming import get_hls_asset_response, get_hls_manifest_response, get_hls_status, get_hls_thumbnail_source
from app.services.media import THUMBNAIL_WIDTH, build_thumbnail_response, thumbnail_placeholder_response
from app.services.media_resolution import generated_thumbnail_cache_path_for_identity
from app.services.streaming import stream_file_response
from app.services.upload_payloads import read_bounded_upload, require_valid_image
from app.services.download_audit import create_download_event
from app.services.zip_utils import build_zip_entries

ResolvedObjectPayload = tuple[Path | None, str, dict[str, Any]]
ResolveObjectPayload = Callable[[], ResolvedObjectPayload]
MAX_CUSTOM_THUMBNAIL_BYTES = 20 * 1024 * 1024
RANGE_STREAM_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class AuthorizedMediaTarget:
    full_path: Path | None
    cache_identity: str | None
    storage_scope: str | None = None
    project_id: str | None = None
    canonical_path: str | None = None
    media_asset_id: str | None = None
    shot_version_id: str | None = None
    exists: bool = True
    display_name: str | None = None
    metadata_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class HlsRouteBuilder:
    base_path: str
    query: str = ''

    def __call__(self, asset_path: str) -> str:
        query_part = f'?{self.query}' if self.query else ''
        return f'{self.base_path}/{asset_path}{query_part}'


@dataclass(frozen=True)
class DownloadAuditSpec:
    fields: dict[str, Any]


def media_target(
    full_path: Path | None,
    cache_identity: str | None,
    *,
    storage_scope: str | None = None,
    project_id: str | None = None,
    canonical_path: str | None = None,
    media_asset_id: str | None = None,
    shot_version_id: str | None = None,
    metadata_payload: dict[str, Any] | None = None,
) -> AuthorizedMediaTarget:
    return AuthorizedMediaTarget(
        full_path=full_path,
        cache_identity=cache_identity,
        storage_scope=storage_scope,
        project_id=project_id,
        canonical_path=canonical_path,
        media_asset_id=media_asset_id,
        shot_version_id=shot_version_id,
        exists=bool(full_path and full_path.exists()),
        display_name=full_path.name if full_path else None,
        metadata_payload=metadata_payload,
    )


def media_target_from_resolved(resolved) -> AuthorizedMediaTarget:
    return AuthorizedMediaTarget(
        full_path=resolved.full_path,
        cache_identity=resolved.cache_identity,
        storage_scope=resolved.storage_scope,
        project_id=getattr(resolved.ref, 'project_id', None),
        canonical_path=resolved.canonical_path,
        media_asset_id=resolved.media_asset_id,
        shot_version_id=resolved.shot_version_id,
        exists=resolved.exists,
        display_name=resolved.full_path.name if resolved.full_path else None,
        metadata_payload=resolved.payload,
    )


def _range_file_response(full_path: Path, range_header: str):
    size = full_path.stat().st_size
    value = str(range_header or '').strip()
    if size <= 0 or not value.lower().startswith('bytes=') or ',' in value:
        return Response(status_code=416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
    start_text, separator, end_text = value[6:].partition('-')
    if not separator:
        return Response(status_code=416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
    try:
        if start_text:
            start = int(start_text)
            end = min(size - 1, int(end_text)) if end_text else size - 1
        else:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise ValueError
            start = max(0, size - suffix_length)
            end = size - 1
    except (TypeError, ValueError):
        return Response(status_code=416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})
    if start < 0 or start >= size or end < start:
        return Response(status_code=416, headers={'Content-Range': f'bytes */{size}', 'Accept-Ranges': 'bytes'})

    length = end - start + 1

    def iter_range():
        remaining = length
        with full_path.open('rb') as source:
            source.seek(start)
            while remaining > 0:
                chunk = source.read(min(RANGE_STREAM_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    media_type = mimetypes.guess_type(full_path.name)[0] or 'application/octet-stream'
    return StreamingResponse(
        iter_range(),
        status_code=206,
        media_type=media_type,
        headers={
            'Accept-Ranges': 'bytes',
            'Content-Range': f'bytes {start}-{end}/{size}',
            'Content-Length': str(length),
        },
    )


def serve_file(target: AuthorizedMediaTarget, db: Session, *, not_found_detail: str = 'File not found', range_header: str | None = None, enable_ranges: bool = False):
    _require_existing_file(target.full_path, detail=not_found_detail)
    if enable_ranges:
        if range_header:
            return _range_file_response(target.full_path, range_header)
        media_type = mimetypes.guess_type(target.full_path.name)[0] or 'application/octet-stream'
        return FileResponse(
            target.full_path,
            media_type=media_type,
            headers={'Accept-Ranges': 'bytes'},
        )
    response = stream_file_response(target.full_path, target.cache_identity or str(target.full_path), db)
    return response


def serve_hls_status(target: AuthorizedMediaTarget, db: Session):
    return get_hls_status(db, job_key=target.cache_identity or str(target.full_path), input_path=target.full_path)


def serve_hls_manifest(target: AuthorizedMediaTarget, db: Session, *, build_asset_url: Callable[[str], str]):
    return get_hls_manifest_response(
        db,
        job_key=target.cache_identity or str(target.full_path),
        input_path=target.full_path,
        build_asset_url=build_asset_url,
    )


def serve_hls_asset(target: AuthorizedMediaTarget, *, asset_path: str, build_asset_url: Callable[[str], str], hls_generation: str | None = None):
    return get_hls_asset_response(
        job_key=target.cache_identity or str(target.full_path),
        asset_path=asset_path,
        build_asset_url=build_asset_url,
        hls_generation=hls_generation,
    )


def serve_thumbnail(
    target: AuthorizedMediaTarget,
    *,
    thumb_path: Path | None = None,
    cached_only: bool = False,
    purge_empty_cache: bool = False,
    preferred_video_source: Path | None = None,
    thumbnail_width: int = THUMBNAIL_WIDTH,
    not_found_detail: str = 'File not found',
    placeholder_on_missing: bool = False,
    allow_cached_without_source: bool = False,
):
    identity = target.cache_identity or str(target.full_path)
    resolved_thumb_path = thumb_path or generated_thumbnail_cache_path_for_identity(identity)
    preferred_source = preferred_video_source
    if preferred_source is None and target.cache_identity:
        preferred_source = get_hls_thumbnail_source(target.cache_identity)

    if not target.full_path or not target.full_path.exists():
        if allow_cached_without_source and resolved_thumb_path.exists() and resolved_thumb_path.stat().st_size > 0:
            return FileResponse(
                resolved_thumb_path,
                media_type='image/jpeg',
                headers={'Cache-Control': 'private, max-age=31536000, immutable'},
            )
        if placeholder_on_missing:
            return thumbnail_placeholder_response()
        raise HTTPException(status_code=404, detail=not_found_detail)

    return build_thumbnail_response(
        target.full_path,
        resolved_thumb_path,
        purge_empty_cache=purge_empty_cache,
        preferred_video_source=preferred_source,
        queue_missing=not cached_only,
        thumbnail_width=thumbnail_width,
    )


def serve_download(
    target: AuthorizedMediaTarget,
    db: Session,
    *,
    request,
    audit: DownloadAuditSpec,
    filename: str | None = None,
    not_found_detail: str = 'File not found',
    audit_before_exists: bool = False,
):
    if audit_before_exists:
        create_download_event(db, request=request, **audit.fields)
        _require_existing_file(target.full_path, detail=not_found_detail)
    else:
        _require_existing_file(target.full_path, detail=not_found_detail)
        create_download_event(db, request=request, **audit.fields)
    return FileResponse(
        target.full_path,
        media_type='application/octet-stream',
        filename=filename or target.full_path.name,
    )


def serve_zip_entries(entries, filename: str, background_tasks, db: Session, *, request, audit: DownloadAuditSpec):
    create_download_event(db, request=request, **audit.fields)
    return build_zip_entries(entries, filename, background_tasks)


def get_object_file_info(resolve_payload: ResolveObjectPayload):
    _full_path, _cache_key, payload = resolve_payload()
    return payload


def stream_object_file(resolve_payload: ResolveObjectPayload, db: Session, *, not_found_detail: str):
    full_path, cache_key, _payload = resolve_payload()
    _require_existing_file(full_path, detail=not_found_detail)
    return stream_file_response(full_path, cache_key, db)


def get_object_hls_status(resolve_payload: ResolveObjectPayload, db: Session):
    full_path, cache_key, _payload = resolve_payload()
    return get_hls_status(db, job_key=cache_key, input_path=full_path)


def get_object_hls_manifest(resolve_payload: ResolveObjectPayload, db: Session, *, build_asset_url: Callable[[str], str]):
    full_path, cache_key, _payload = resolve_payload()
    return get_hls_manifest_response(
        db,
        job_key=cache_key,
        input_path=full_path,
        build_asset_url=build_asset_url,
    )


def get_object_hls_asset(resolve_payload: ResolveObjectPayload, *, asset_path: str, build_asset_url: Callable[[str], str], hls_generation: str | None = None):
    _full_path, cache_key, _payload = resolve_payload()
    return get_hls_asset_response(
        job_key=cache_key,
        asset_path=asset_path,
        build_asset_url=build_asset_url,
        hls_generation=hls_generation,
    )


def download_object_file(resolve_payload: ResolveObjectPayload, *, not_found_detail: str):
    full_path, _cache_key, _payload = resolve_payload()
    _require_existing_file(full_path, detail=not_found_detail)
    return FileResponse(full_path, media_type='application/octet-stream', filename=full_path.name)


def get_object_thumbnail(resolve_payload: ResolveObjectPayload, db: Session, *, not_found_detail: str, queue_missing: bool = True):
    full_path, cache_key, _payload = resolve_payload()
    db.close()
    return serve_thumbnail(
        media_target(full_path, cache_key),
        cached_only=not queue_missing,
        not_found_detail=not_found_detail,
        placeholder_on_missing=True,
        allow_cached_without_source=True,
    )


async def set_object_thumbnail(resolve_payload: ResolveObjectPayload, *, file, not_found_detail: str):
    full_path, cache_key, _payload = resolve_payload()
    _require_existing_file(full_path, detail=not_found_detail)
    if not cache_key:
        raise HTTPException(status_code=409, detail='Thumbnail target is missing a cache identity')

    contents = await read_bounded_upload(
        file,
        max_bytes=MAX_CUSTOM_THUMBNAIL_BYTES,
        empty_detail='Thumbnail image is empty',
        too_large_detail='Thumbnail image is too large',
    )

    require_valid_image(contents, detail='Thumbnail image is invalid')
    image = Image.open(BytesIO(contents))
    image = ImageOps.exif_transpose(image)

    if image.mode in {'RGBA', 'LA'} or 'transparency' in image.info:
        image = image.convert('RGBA')
        background = Image.new('RGBA', image.size, (0, 0, 0, 255))
        background.alpha_composite(image)
        image = background.convert('RGB')
    else:
        image = image.convert('RGB')

    max_height = max(320, THUMBNAIL_WIDTH * 4)
    image.thumbnail((THUMBNAIL_WIDTH, max_height), Image.Resampling.LANCZOS)

    thumb_path = generated_thumbnail_cache_path_for_identity(cache_key)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = thumb_path.with_name(f'{thumb_path.name}.{uuid4().hex}.tmp')
    try:
        image.save(temp_path, format='JPEG', quality=90, optimize=True, progressive=True)
        temp_path.replace(thumb_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return {
        'status': 'success',
        'thumbnail_url_cache_bust': int(time.time() * 1000),
    }


def _require_existing_file(full_path: Path | None, *, detail: str):
    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail=detail)
