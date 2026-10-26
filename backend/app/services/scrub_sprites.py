"""Hover-scrub sprite sheets.

One small JPEG holds a grid of evenly spaced frames from a video. Browsers
scrub by moving the sheet behind a fixed frame, so they never decode video.
Sheets are queued when a tracker version is added and made on demand for
anything older. Generation is CPU only, runs one at a time at low priority,
and prefers the 720p review proxy over the original file.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image

from app.services.hls_streaming import get_hls_thumbnail_source
from app.services.media import VIDEO_EXTENSIONS, get_video_duration_quick
from app.services.media_resolution import scrub_sprite_cache_path_for_identity

logger = logging.getLogger(__name__)

# The frontend uses the same grid; change SCRUB_SPRITE_CACHE_VERSION with it.
SCRUB_COLUMNS = 6
SCRUB_ROWS = 5
SCRUB_FRAME_WIDTH = 320
SCRUB_FRAME_HEIGHT = 180
SCRUB_FRAMES = SCRUB_COLUMNS * SCRUB_ROWS
SCRUB_JPEG_QUALITY = 78
FRAME_BYTES = SCRUB_FRAME_WIDTH * SCRUB_FRAME_HEIGHT * 3

# Shorter clips are read in one pass; longer ones by seeking to each sample,
# so the cost stays flat however long or heavy the source is.
SEEK_SAMPLING_MIN_SECONDS = 30
PASS_TIMEOUT_SECONDS = 90
SEEK_TIMEOUT_SECONDS = 15
# On-demand requests share a small queue; versions added in bulk may wait longer.
ON_DEMAND_MAX_PENDING = 8
WARMUP_MAX_PENDING = 2000
FAILURE_RETRY_SECONDS = 15 * 60

FRAME_FILTER = ','.join((
    'scale=ceil(iw*sar/2)*2:ih',
    'setsar=1',
    # Match the 16:9 cover crop of tracker cards.
    f'scale={SCRUB_FRAME_WIDTH}:{SCRUB_FRAME_HEIGHT}:force_original_aspect_ratio=increase',
    f'crop={SCRUB_FRAME_WIDTH}:{SCRUB_FRAME_HEIGHT}',
    'format=rgb24',
))

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='scrub-sprite')
_lock = threading.Lock()
_pending: set[str] = set()
_failed_until: dict[str, float] = {}


def _ffmpeg(*args: str) -> list[str]:
    nice = shutil.which('nice')
    return [*([nice, '-n', '10'] if nice else []), 'ffmpeg', '-hide_banner', '-nostdin', '-nostats', '-loglevel', 'error', *args]


def _raw_output() -> list[str]:
    return ['-an', '-sn', '-dn', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']


def _frames_in_one_pass(source: Path, duration: float) -> list[bytes]:
    # Each sample sits in the middle of its slice of the clip.
    rate = SCRUB_FRAMES / max(duration, 0.1)
    command = _ffmpeg(
        '-threads', '2', '-i', str(source),
        '-vf', f'fps={rate:.6f},{FRAME_FILTER}',
        '-frames:v', str(SCRUB_FRAMES), *_raw_output(),
    )
    data = subprocess.run(command, capture_output=True, timeout=PASS_TIMEOUT_SECONDS, check=True).stdout
    return [data[index:index + FRAME_BYTES] for index in range(0, len(data) - FRAME_BYTES + 1, FRAME_BYTES)]


def _frames_by_seeking(source: Path, duration: float) -> list[bytes]:
    frames = []
    for index in range(SCRUB_FRAMES):
        seek = (index + 0.5) * duration / SCRUB_FRAMES
        command = _ffmpeg(
            '-threads', '1', '-ss', f'{seek:.3f}', '-i', str(source),
            '-vf', FRAME_FILTER, '-frames:v', '1', *_raw_output(),
        )
        data = subprocess.run(command, capture_output=True, timeout=SEEK_TIMEOUT_SECONDS, check=True).stdout
        if len(data) >= FRAME_BYTES:
            frames.append(data[:FRAME_BYTES])
    return frames


def _save_sheet(frames: list[bytes], output: Path) -> None:
    sheet = Image.new('RGB', (SCRUB_FRAME_WIDTH * SCRUB_COLUMNS, SCRUB_FRAME_HEIGHT * SCRUB_ROWS))
    for index in range(SCRUB_FRAMES):
        # A clip with too few frames repeats its last one to fill the grid.
        frame = Image.frombytes('RGB', (SCRUB_FRAME_WIDTH, SCRUB_FRAME_HEIGHT), frames[min(index, len(frames) - 1)])
        sheet.paste(frame, ((index % SCRUB_COLUMNS) * SCRUB_FRAME_WIDTH, (index // SCRUB_COLUMNS) * SCRUB_FRAME_HEIGHT))
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f'{output.stem}.{uuid.uuid4().hex}.part.jpg')
    try:
        sheet.save(partial, format='JPEG', quality=SCRUB_JPEG_QUALITY, optimize=True, progressive=True)
        partial.replace(output)
    finally:
        partial.unlink(missing_ok=True)


def _render(full_path: Path, cache_identity: str, output: Path) -> bool:
    # Resolve the source when the job runs; the review proxy may be ready by then.
    source = get_hls_thumbnail_source(cache_identity) or full_path
    duration = get_video_duration_quick(source)
    if duration <= 0:
        return False
    try:
        sample = _frames_by_seeking if duration >= SEEK_SAMPLING_MIN_SECONDS else _frames_in_one_pass
        frames = sample(source, duration)
    except subprocess.CalledProcessError as error:
        logger.warning('Scrub sprite failed for %s: %s', full_path.name, (error.stderr or b'').decode(errors='replace').strip()[-300:])
        return False
    except subprocess.TimeoutExpired:
        logger.warning('Scrub sprite timed out for %s', full_path.name)
        return False
    if not frames:
        return False
    _save_sheet(frames, output)
    return True


def _run_job(full_path: Path, cache_identity: str, output: Path) -> None:
    key = str(output)
    try:
        if not output.exists() and not _render(full_path, cache_identity, output):
            with _lock:
                _failed_until[key] = time.monotonic() + FAILURE_RETRY_SECONDS
    except Exception:
        logger.exception('Scrub sprite job crashed for %s', full_path.name)
        with _lock:
            _failed_until[key] = time.monotonic() + FAILURE_RETRY_SECONDS
    finally:
        with _lock:
            _pending.discard(key)


def _queue(full_path: Path, cache_identity: str, *, max_pending: int) -> bool:
    """Queue a sheet. Return False when it recently failed and should not retry yet."""
    output = scrub_sprite_cache_path_for_identity(cache_identity)
    key = str(output)
    with _lock:
        if _failed_until.get(key, 0) > time.monotonic():
            return False
        _failed_until.pop(key, None)
        if key in _pending or len(_pending) >= max_pending:
            return True
        _pending.add(key)
    _executor.submit(_run_job, full_path, cache_identity, output)
    return True


def queue_scrub_sprite_warmup(full_path: Path | None, cache_identity: str | None) -> bool:
    """Queue a sheet for a newly added video version."""
    if not cache_identity or not full_path or full_path.suffix.lower() not in VIDEO_EXTENSIONS or not full_path.exists():
        return False
    sprite = scrub_sprite_cache_path_for_identity(cache_identity)
    if sprite.exists() and sprite.stat().st_size > 0:
        return False
    return _queue(full_path, cache_identity, max_pending=WARMUP_MAX_PENDING)


def scrub_sprite_response(full_path: Path | None, cache_identity: str | None):
    """Serve the cached sheet, or start making it and answer 202."""
    if not cache_identity or not full_path or full_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=404, detail='No scrub preview for this media')
    sprite = scrub_sprite_cache_path_for_identity(cache_identity)
    if sprite.exists() and sprite.stat().st_size > 0:
        return FileResponse(sprite, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=31536000, immutable'})
    if not full_path.exists():
        raise HTTPException(status_code=404, detail='Media file not found')
    if not _queue(full_path, cache_identity, max_pending=ON_DEMAND_MAX_PENDING):
        raise HTTPException(status_code=404, detail='Scrub preview is not available for this media')
    return Response(status_code=202, headers={'Cache-Control': 'no-store', 'Retry-After': '2'})


def queue_scrub_sprites_for_assets(media_asset_ids: list[str]) -> int:
    """Queue sheets for versions that were just added. Runs off the request path."""
    from app.db import SessionLocal
    from app.models import MediaAsset
    from app.services.media_resolution import resolve_media_asset_path

    ids = list(dict.fromkeys(asset_id for asset_id in media_asset_ids if asset_id))
    if not ids:
        return 0
    queued = 0
    db = SessionLocal()
    try:
        for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(ids)).all():
            try:
                full_path, cache_identity, _scope = resolve_media_asset_path(asset, db=db)
                queued += queue_scrub_sprite_warmup(full_path, cache_identity)
            except Exception:
                logger.exception('Could not queue scrub sprite for media asset %s', asset.id)
        db.commit()
    finally:
        db.close()
    return queued
