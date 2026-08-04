from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.runtime_state import _faststart_in_progress, _faststart_lock, executor
from app.services.hls_streaming import ensure_hls_package_running
from app.services.media import is_video
from app.services.media_assets import resolve_media_asset_cache_target
from app.services.media_metadata import get_cached_video_info
from app.services.media_resolution import resolve_media_full_path

logger = logging.getLogger(__name__)


def apply_faststart_remux_fs_path(file_fs_path: Path) -> None:
    tmp_path = file_fs_path.with_suffix(file_fs_path.suffix + '.faststart.tmp')
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(file_fs_path), '-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', str(tmp_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
        tmp_path.replace(file_fs_path)
        return
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass
    if (result.stderr or '').strip():
        logger.warning('Faststart remux failed')


def _apply_faststart_remux(file_path: str, project_id: Optional[str] = None):
    try:
        full_path, _job_key = resolve_media_full_path(file_path, project_id, storage_scope='tracker_version')
        if not full_path or not full_path.is_file():
            return
        apply_faststart_remux_fs_path(full_path)
    except subprocess.TimeoutExpired:
        logger.warning('Faststart remux timed out')
        try:
            full_path, _job_key = resolve_media_full_path(file_path, project_id, storage_scope='tracker_version')
            if full_path:
                tmp_path = Path(str(full_path) + '.faststart.tmp')
                if tmp_path.exists():
                    tmp_path.unlink()
        except Exception:
            pass
    except Exception as exc:
        logger.warning('Faststart remux failed (%s)', type(exc).__name__)
    finally:
        with _faststart_lock:
            _faststart_in_progress.discard(file_path)


def trigger_faststart_fix(file_path: str, project_id: Optional[str] = None):
    if not file_path:
        return
    ext = Path(file_path).suffix.lower()
    if ext not in {'.mp4', '.m4v'}:
        return

    with _faststart_lock:
        if file_path in _faststart_in_progress:
            return
        _faststart_in_progress.add(file_path)

    full_path, _job_key = resolve_media_full_path(file_path, project_id, storage_scope='tracker_version')
    if not full_path or not full_path.is_file():
        with _faststart_lock:
            _faststart_in_progress.discard(file_path)
        return

    executor.submit(_apply_faststart_remux, file_path, project_id)


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
