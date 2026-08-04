from __future__ import annotations

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.services.file_metadata import build_file_metadata
from app.services.media_serving import media_target_from_resolved, serve_file, serve_thumbnail
from app.services.media_resolution import generated_thumbnail_cache_path_for_identity
from app.services.zip_utils import build_zip_entries

from app.services._project_content_gateway_impl import ContentAccessPolicy, ContentRef, collect_zip, resolve_content


def build_metadata(policy: ContentAccessPolicy, ref: ContentRef) -> dict:
    resolved = resolve_content(policy, ref, purpose='metadata')
    if resolved.payload is not None:
        return resolved.payload
    if not resolved.full_path or not resolved.full_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    return build_file_metadata(resolved.full_path, resolved.canonical_path or ref.path)


def stream_content(policy: ContentAccessPolicy, ref: ContentRef, db: Session):
    resolved = resolve_content(policy, ref, purpose='stream')
    return serve_file(media_target_from_resolved(resolved), db)


def thumbnail_content(policy: ContentAccessPolicy, ref: ContentRef, db: Session, *, cached_only: bool = False):
    resolved = resolve_content(policy, ref, purpose='thumbnail')
    if not resolved.full_path or not resolved.full_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    identity = resolved.cache_identity or str(resolved.full_path)
    return serve_thumbnail(
        media_target_from_resolved(resolved),
        thumb_path=generated_thumbnail_cache_path_for_identity(identity),
        cached_only=cached_only,
    )


def build_zip_response(policy: ContentAccessPolicy, raw_paths: list[str], filename: str, background_tasks: BackgroundTasks) -> FileResponse:
    return build_zip_entries(collect_zip(policy, raw_paths), filename, background_tasks)
