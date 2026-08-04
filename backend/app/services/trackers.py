from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.services.media import VIDEO_EXTENSIONS, get_video_info
from app.services.projects import get_project_dir

_tracker_write_locks: dict[str, threading.RLock] = {}
_tracker_write_locks_guard = threading.Lock()


def _tracker_file(project_id: str, tracker_name: str) -> Path:
    return get_project_dir(project_id) / f'{tracker_name}.tracker.json'


def get_tracker_write_lock(project_id: str, tracker_name: str) -> threading.RLock:
    key = f'{project_id}:{tracker_name}'
    with _tracker_write_locks_guard:
        lock = _tracker_write_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _tracker_write_locks[key] = lock
        return lock


def load_tracker(project_id: str, tracker_name: str) -> dict:
    tracker_file = _tracker_file(project_id, tracker_name)
    if not tracker_file.exists():
        raise HTTPException(status_code=404, detail='Tracker not found')
    with open(tracker_file, 'r') as handle:
        return json.load(handle)


def save_tracker(project_id: str, tracker_name: str, tracker_data: dict, *, compute_stats: bool = False) -> None:
    tracker_file = _tracker_file(project_id, tracker_name)
    tracker_file.parent.mkdir(parents=True, exist_ok=True)
    lock = get_tracker_write_lock(project_id, tracker_name)
    with lock:
        if compute_stats:
            try:
                tracker_data['stats'] = compute_tracker_stats(project_id, tracker_data)
            except Exception:
                print('Warning: failed to compute tracker stats')
        temp_file = tracker_file.with_name(f'{tracker_file.name}.{uuid.uuid4().hex}.tmp')
        try:
            with open(temp_file, 'w') as handle:
                json.dump(tracker_data, handle, indent=2)
            os.replace(temp_file, tracker_file)
        finally:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass


def queue_thumbnail_warmup_for_paths(file_paths: list[str], *, db=None, project_id: str | None = None, storage_scope: str | None = None) -> int:
    from app.services.media import get_safe_path, queue_thumbnail_generation
    from app.services.hls_streaming import get_hls_thumbnail_source
    from app.services.media_assets import resolve_media_asset_cache_target
    from app.services.media_resolution import generated_thumbnail_cache_path_for_identity, thumbnail_cache_path_for_media

    queued = 0
    for file_path in file_paths or []:
        full_path = None
        thumb_path = None

        if db is not None and project_id:
            full_path, cache_key, _asset = resolve_media_asset_cache_target(
                db,
                project_id,
                file_path,
                storage_scope=storage_scope or 'project',
            )
            if full_path and cache_key:
                thumb_path = generated_thumbnail_cache_path_for_identity(cache_key)
        else:
            try:
                full_path = get_safe_path(file_path)
            except Exception:
                full_path = None
            if full_path and full_path.exists():
                thumb_path = thumbnail_cache_path_for_media(project_id, file_path, full_path, storage_scope=storage_scope)

        if not full_path or not full_path.exists() or not thumb_path:
            continue
        if full_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if thumb_path.exists() and thumb_path.stat().st_size > 0:
            continue
        thumbnail_source = get_hls_thumbnail_source(cache_key) if cache_key else None
        queue_thumbnail_generation(thumbnail_source if thumbnail_source and thumbnail_source.exists() else full_path, thumb_path)
        queued += 1
    return queued


def compute_tracker_stats(project_id: str, tracker: dict, storage_scope: str | None = 'tracker_version') -> dict:
    from app.services.media_resolution import resolve_media_target

    status_order = ['not_started', 'in_progress', 'waiting_review', 'edits_requested', 'done']
    status_labels = {
        'not_started': 'Not Started',
        'in_progress': 'In Progress',
        'waiting_review': 'Review',
        'edits_requested': 'Edits Requested',
        'done': 'Done',
    }
    shots = tracker.get('shots', [])
    total_duration = 0.0
    total_frames = 0
    total_versions = 0
    shots_with_latest_video = 0
    status_counts = {status: 0 for status in status_order}

    for shot in shots:
        status = str(shot.get('status') or 'not_started')
        status_counts[status] = status_counts.get(status, 0) + 1
        versions = shot.get('versions', [])
        total_versions += len(versions)
        if not versions:
            continue
        latest = versions[-1]
        file_path = latest.get('file_path', '')
        full_path, _job_key, _resolved_scope = resolve_media_target(file_path, project_id, storage_scope=storage_scope)
        if full_path and full_path.exists() and full_path.suffix.lower() in VIDEO_EXTENSIONS:
            info = get_video_info(full_path)
            duration = float(info.get('duration', 0) or 0)
            frames = int(info.get('frames', 0) or 0)
            total_duration += duration
            total_frames += frames
            if duration > 0 or frames > 0:
                shots_with_latest_video += 1

    average_versions_per_shot = round(total_versions / len(shots), 2) if shots else 0.0
    average_shot_duration = round(total_duration / shots_with_latest_video, 2) if shots_with_latest_video else 0.0

    return {
        'totalDuration': round(total_duration, 2),
        'totalFrames': total_frames,
        'totalShots': len(shots),
        'totalVersions': total_versions,
        'averageVersionsPerShot': average_versions_per_shot,
        'averageShotDuration': average_shot_duration,
        'statusBreakdown': [
            {
                'status': status,
                'label': status_labels.get(status, status.replace('_', ' ').title()),
                'count': status_counts.get(status, 0),
            }
            for status in status_order
        ],
        'computed_at': time.time(),
    }
