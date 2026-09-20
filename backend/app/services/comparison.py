"""Authorized, cached two-up previews. One encoded frame contains both versions."""
from __future__ import annotations

import json
import math
import subprocess
import threading
import time
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.db import SessionLocal
from app.models import HorizonShotVersion, HorizonTracker, TranscodeJob
from app.runtime_state import executor, transcode_cancel_requested, transcode_processes, transcode_progress
from app.services.media import get_file_hash, is_video
from app.services.media_processing import MediaProcess
from app.services.media_resolution import source_signature, transcode_cache_path_for_identity
from app.services.storage_capacity import ensure_data_capacity
from app.services.horizons.tracker_settings import tracker_tool_enabled_for_context
from app.services.transcode_lifecycle import (
    claim_transcode_job, mark_transcode_complete, mark_transcode_error,
    maybe_renew_transcode_claim, owns_transcode_claim, release_transcode_claim,
    restore_transcode_identity_for_authorized_source, touch_transcode_access,
    transcode_claim_is_active, transcode_identity_is_cancelled, transcode_publish_guard,
)

_queue_guard = threading.Lock()
_pending: set[str] = set()
_ERROR = 'The comparison could not be prepared. Check that both media files are online, then retry.'


@lru_cache(maxsize=256)
def _probe(path: str, signature: str) -> tuple[Fraction, Fraction, bool, tuple[int, int]]:
    # The signature is part of the cache key. Never reuse metadata after replacement.
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist',
            'mov,matroska,webm,avi,mxf,mpegvideo,mpegts', '-select_streams', 'v:0', '-show_entries',
            'stream=r_frame_rate,avg_frame_rate,nb_frames,duration,duration_ts,time_base,width,height,sample_aspect_ratio:stream_tags=DURATION:stream_side_data=rotation',
            '-of', 'json', path,
        ], capture_output=True, text=True, timeout=30, check=True)
        metadata = json.loads(result.stdout)
        stream = metadata['streams'][0]
        rate = Fraction(stream.get('avg_frame_rate') or '0/1') if stream.get('avg_frame_rate') != '0/0' else Fraction(0)
        if not rate:
            rate = Fraction(stream['r_frame_rate'])
        if not 1 <= rate <= 120:
            raise ValueError('Unsupported frame rate')
        frames = stream.get('nb_frames')
        if frames and frames != 'N/A':
            duration = Fraction(int(frames), 1) / rate
        elif stream.get('duration') not in (None, 'N/A'):
            duration = Fraction(str(stream['duration']))
        elif stream.get('duration_ts') not in (None, 'N/A'):
            duration = int(stream['duration_ts']) * Fraction(stream['time_base'])
        else:
            hours, minutes, seconds = stream['tags']['DURATION'].split(':')
            duration = int(hours) * 3600 + int(minutes) * 60 + Fraction(seconds)
        # Never substitute the container's duration: an audio track can be
        # longer than the picture and would hide the true last video frame.
        if not 0 < duration <= 86400:
            raise ValueError('Unsupported duration')
        nominal = stream.get('r_frame_rate')
        aspect = stream.get('sample_aspect_ratio') or '1:1'
        sar = Fraction(aspect.replace(':', '/')) if aspect not in ('N/A', '0:1') else Fraction(1)
        width, height = round(int(stream['width']) * sar), int(stream['height'])
        rotation = next((item['rotation'] for item in stream.get('side_data_list', []) if 'rotation' in item), 0)
        if abs(round(rotation)) % 180 == 90:
            width, height = height, width
        if not 1 <= width <= 32768 or not 1 <= height <= 32768:
            raise ValueError('Unsupported video dimensions')
        return rate, duration, nominal in (None, '0/0') or rate != Fraction(nominal), (width, height)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, ZeroDivisionError) as exc:
        raise HTTPException(422, 'Video timing could not be read. Choose another version.') from exc


@dataclass(frozen=True)
class Comparison:
    key: str
    paths: tuple[Path, Path]
    signatures: tuple[str, str]
    recipe: dict
    info: dict
    artwork: bytes | None = None

    @property
    def output(self):
        return transcode_cache_path_for_identity(self.key)


def resolve_comparison(db, primary, secondary, *, user=None, access_role=None, share=False) -> Comparison:
    """Inputs MUST come from the existing authenticated/shared object resolvers."""
    versions = [db.get(HorizonShotVersion, item.shot_version_id) for item in (primary, secondary)]
    if (not all(versions) or versions[0].id == versions[1].id
            or versions[0].project_id != versions[1].project_id or versions[0].shot_id != versions[1].shot_id):
        raise HTTPException(400, 'Choose two versions of the same shot.')
    tracker = db.get(HorizonTracker, versions[0].tracker_id)
    if not tracker or not tracker_tool_enabled_for_context(tracker, 'comparison', user=user, access_role=access_role, share=share):
        raise HTTPException(403, 'Comparison is not available in this tracker.')
    entries = []
    for item in (primary, secondary):
        if not item.exists or not item.full_path or not item.full_path.is_file():
            raise HTTPException(404, 'A comparison source is offline.')
        if not is_video(item.full_path) or not item.cache_identity:
            raise HTTPException(400, 'Choose two video versions.')
        signature = source_signature(item.full_path)
        entries.append((get_file_hash(item.cache_identity), item.full_path, signature))
    primary_left = entries[0][0] <= entries[1][0]
    ordered = sorted(entries, key=lambda item: item[0])
    timing = [_probe(str(path), signature) for _, path, signature in ordered]
    # Preserve the faster source's temporal detail. Unlike equal-rate versions,
    # different-rate versions compare elapsed time, not matching frame numbers.
    rate = max(item[0] for item in timing).limit_denominator(1001)
    if rate.numerator > 240000:
        rate = Fraction(round(float(rate) * 1000), 1000)
    ends = [math.ceil(item[1] * rate) for item in timing]
    frames = max(ends)
    recipe = {'kind': 'comparison', 'rate_n': rate.numerator, 'rate_d': rate.denominator, 'frames': frames}
    key = 'artifact:comparison:v1:' + ':'.join(item[0] for item in ordered)
    key += ':' + get_file_hash(':'.join(item[2] for item in ordered))
    # Object resolution can cache media metadata in this session. Finish that
    # transaction before the worker/access ledger opens its own write session.
    # Otherwise a cold SQLite installation waits on its own metadata write.
    db.commit()
    return Comparison(key, tuple(item[1] for item in ordered), tuple(item[2] for item in ordered), recipe, {
        'fps': float(rate), 'frame_count': frames,
        'end_frames': ends if primary_left else ends[::-1], 'primary_is_left': primary_left,
        'different_frame_rates': timing[0][0] != timing[1][0] or any(item[2] for item in timing),
        'source_sizes': [item[3] for item in (timing if primary_left else timing[::-1])],
        'can_export': True,
    })


def _prepare(pair: Comparison, attempt=None):
    temporary = None
    artwork_path = None
    process = None
    try:
        if attempt is None:
            with SessionLocal() as db:
                attempt = claim_transcode_job(db, job_key=pair.key, output_path=pair.output)
        if attempt is None or transcode_identity_is_cancelled(pair.key):
            return
        # A second process can have completed the same pair while this was queued.
        if pair.output.is_file() and pair.output.stat().st_size > 0:
            mark_transcode_complete(attempt, output_path=pair.output)
            return
        duration = pair.recipe['frames'] * pair.recipe['rate_d'] / pair.recipe['rate_n']
        bitrate = 22_000_000 if pair.recipe['kind'] == 'comparison_export' else 14_000_000
        ensure_data_capacity(math.ceil(duration * bitrate / 8))
        temporary = pair.output.with_name(f'{pair.output.stem}.{attempt.attempt_id}.part.mp4')
        inputs = pair.paths
        if pair.artwork:
            artwork_path = temporary.with_suffix('.png')
            artwork_path.write_bytes(pair.artwork)
            inputs = (*inputs, artwork_path)
        process = MediaProcess(inputs, temporary, pair.recipe)
        transcode_processes[pair.key] = process
        heartbeat = time.time()
        for line in process.stdout:
            if transcode_identity_is_cancelled(pair.key) or not owns_transcode_claim(attempt):
                raise RuntimeError('Cancelled')
            heartbeat = maybe_renew_transcode_claim(attempt, heartbeat)
            if line.startswith('out_time_ms='):
                ensure_data_capacity()
                try:
                    progress = min(99, max(0, int(line.split('=', 1)[1]) / 1_000_000 / duration * 100))
                    transcode_progress[pair.key]['progress'] = round(progress, 1)
                except ValueError:
                    pass
        if process.wait() != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError('Encoding failed')
        actual_rate, actual_duration, _, _ = _probe(str(temporary), source_signature(temporary))
        if actual_rate != Fraction(pair.recipe['rate_n'], pair.recipe['rate_d']) or round(actual_duration * actual_rate) != pair.recipe['frames']:
            raise RuntimeError('Unexpected output timing')
        with transcode_publish_guard(pair.key, attempt):
            if pair.key in transcode_cancel_requested or not owns_transcode_claim(attempt):
                raise RuntimeError('Cancelled')
            if tuple(source_signature(path) for path in pair.paths) != pair.signatures:
                raise RuntimeError('Source changed')
            temporary.replace(pair.output)
        mark_transcode_complete(attempt, output_path=pair.output, duration=duration)
    except Exception:
        if attempt:
            mark_transcode_error(attempt, error=_ERROR)
    finally:
        try:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except Exception:
                    process.kill()
        finally:
            try:
                if temporary:
                    temporary.unlink(missing_ok=True)
                if artwork_path:
                    artwork_path.unlink(missing_ok=True)
            finally:
                try:
                    if attempt:
                        release_transcode_claim(attempt)
                finally:
                    with _queue_guard:
                        _pending.discard(pair.key)


def comparison_status(db, pair: Comparison, *, retry=False, start=True):
    if start:
        restore_transcode_identity_for_authorized_source(pair.key)
    if pair.output.is_file() and pair.output.stat().st_size > 0:
        return {**pair.info, 'status': 'complete', 'progress': 100}
    if transcode_claim_is_active(pair.key):
        state = transcode_progress.get(pair.key, {})
        return {**pair.info, 'status': 'processing', 'progress': state.get('progress', 0)}
    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == pair.key).first()
    if job and job.status == 'error' and not retry:
        return {**pair.info, 'status': 'error', 'error': _ERROR}
    if not start:
        return {**pair.info, 'status': 'queued', 'progress': 0} if pair.key in _pending else {
            **pair.info, 'status': 'error', 'error': 'This export is no longer available. Export it again.',
        }
    # Bound work instead of precomputing every combination of shot versions.
    # Existing leases serialize duplicate requests across backend processes.
    with _queue_guard:
        if not _pending:
            _pending.add(pair.key)
            attempt = None
            try:
                if pair.recipe['kind'] == 'comparison_export':
                    # Publish the existing durable lease before returning a receipt.
                    # Status requests on another worker must see accepted work too.
                    attempt = claim_transcode_job(db, job_key=pair.key, output_path=pair.output)
                    if attempt is None:
                        raise HTTPException(409, 'The export could not start. Try again.')
                executor.submit(_prepare, pair, attempt)
            except Exception:
                _pending.discard(pair.key)
                if attempt:
                    mark_transcode_error(attempt, error=_ERROR)
                    release_transcode_claim(attempt)
                raise
        elif pair.recipe['kind'] == 'comparison_export' and pair.key not in _pending:
            raise HTTPException(429, 'Another video is being prepared. Try again shortly.', headers={'Retry-After': '5'})
    return {**pair.info, 'status': 'queued', 'progress': 0}


def comparison_file(pair: Comparison, *, filename: str | None = None):
    touch_transcode_access(pair.key)
    if not pair.output.is_file():
        raise HTTPException(404, 'Prepare the comparison again.')
    return FileResponse(pair.output, filename=filename, media_type='video/mp4', headers={'Cache-Control': 'private, no-store'})
