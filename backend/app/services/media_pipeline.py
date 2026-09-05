from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.hls_streaming import ensure_hls_package_running
from app.services.media import is_video
from app.services.media_assets import resolve_media_asset_cache_target
from app.services.media_metadata import get_cached_video_info
from app.services.media_resolution import resolve_media_full_path


def trigger_auto_hls_package(file_path: str, db: Session, project_id: Optional[str] = None, *, storage_scope: str = 'tracker_version'):
    if not file_path:
        return

    safe_path = None
    job_key = None
    asset = None
    if project_id:
        safe_path, job_key, asset = resolve_media_asset_cache_target(
            db,
            project_id,
            file_path,
            storage_scope=storage_scope,
        )
    else:
        safe_path, job_key = resolve_media_full_path(file_path, project_id, storage_scope=storage_scope)

    if not safe_path or not safe_path.is_file() or not job_key or not is_video(safe_path):
        return

    get_cached_video_info(
        db,
        safe_path,
        file_path,
        project_id=project_id,
        storage_scope=storage_scope,
        media_asset_id=getattr(asset, 'id', None),
        cache_identity=job_key,
    )
    ensure_hls_package_running(db, job_key=job_key, input_path=safe_path)
