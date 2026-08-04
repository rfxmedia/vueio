from __future__ import annotations

import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import TranscodeJob
from app.runtime_state import executor, transcode_cancel_requested, transcode_processes, transcode_progress
from app.services.media import get_video_info, is_video, needs_transcode
from app.services.media_resolution import transcode_cache_path_for_identity
from app.services.media_resolution import source_signature
from app.services.storage_capacity import ensure_data_capacity
from app.services.transcode_lifecycle import (
    cancel_all_transcodes,
    claim_transcode_job,
    cleanup_transcode_runtime_state,
    enforce_transcode_cache_budget,
    mark_transcode_complete,
    mark_transcode_error,
    maybe_renew_transcode_claim,
    mp4_job_key,
    owns_transcode_claim,
    release_transcode_claim,
    restore_transcode_identity_for_authorized_source,
    transcode_claim_is_active,
    transcode_publish_guard,
    touch_transcode_access,
)

settings = get_settings()


def clear_transcode_cache(db: Session) -> dict:
    cancelled_jobs = cancel_all_transcodes()

    entries_removed = 0
    for path in settings.transcode_dir.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        if path.name != '.locks':
            entries_removed += 1

    jobs_removed = db.query(TranscodeJob).delete(synchronize_session=False)
    cleanup_transcode_runtime_state()
    db.commit()
    return {
        'status': 'cleared',
        'entries_removed': entries_removed,
        'jobs_removed': jobs_removed,
        'cancelled_jobs': cancelled_jobs,
    }


def _is_nonempty_file(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except Exception:
        return False


def _estimated_mp4_output_bytes(input_path: Path, duration: float | None = None) -> int:
    if duration is None:
        try:
            duration = float(get_video_info(input_path).get('duration') or 0)
        except Exception:
            duration = 0
    if duration and duration > 0:
        # CRF output is variable; 30 Mbps plus headroom is a conservative
        # estimate for the configured review proxy, and the worker rechecks the
        # reserve while ffmpeg is running.
        return max(1024 * 1024, int(duration * 30_000_000 / 8 * 1.15))
    try:
        return max(1024 * 1024, input_path.stat().st_size)
    except OSError:
        return 1024 * 1024


def _adopt_legacy_mp4_artifact(db: Session, *, legacy_job_key: str, artifact_job_key: str, artifact_path: Path) -> bool:
    if legacy_job_key == artifact_job_key:
        return False
    if _is_nonempty_file(artifact_path):
        return True
    if transcode_claim_is_active(artifact_job_key):
        return False

    legacy_job = db.query(TranscodeJob).filter(TranscodeJob.file_path == legacy_job_key).first()
    candidates: list[Path] = []
    if legacy_job and legacy_job.status == 'complete' and legacy_job.output_path:
        candidates.append(Path(legacy_job.output_path))
    candidates.append(transcode_cache_path_for_identity(legacy_job_key))
    legacy_path = next((path for path in candidates if _is_nonempty_file(path)), None)
    if legacy_path is None:
        return False
    ensure_data_capacity(legacy_path.stat().st_size)

    attempt = claim_transcode_job(db, job_key=artifact_job_key, output_path=artifact_path)
    if attempt is None:
        return False

    tmp_path = artifact_path.with_name(f'{artifact_path.stem}.{attempt.attempt_id}.{uuid4().hex}.adopt{artifact_path.suffix}')
    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, tmp_path)
        if not _is_nonempty_file(tmp_path):
            raise RuntimeError('legacy MP4 artifact validation failed')
        with transcode_publish_guard(artifact_job_key, attempt):
            if not _is_nonempty_file(tmp_path):
                raise RuntimeError('legacy MP4 artifact validation failed')
            tmp_path.replace(artifact_path)
        tmp_path = None

        job = db.query(TranscodeJob).filter(TranscodeJob.file_path == artifact_job_key).first()
        if not job:
            job = TranscodeJob(file_path=artifact_job_key, created_at=time.time())
            db.add(job)
        job.status = 'complete'
        job.progress = 100
        job.output_path = str(artifact_path)
        job.last_accessed = time.time()
        if legacy_job:
            job.duration = legacy_job.duration or job.duration or 0
            db.delete(legacy_job)
        db.commit()
        enforce_transcode_cache_budget(db)
        return True
    except Exception as exc:
        mark_transcode_error(attempt, error=str(exc))
        return False
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        release_transcode_claim(attempt)


def _start_or_restart_transcode_job(db: Session, job_key: str, output_path: Path) -> TranscodeJob:
    try:
        if output_path.exists() and output_path.is_file() and output_path.stat().st_size == 0:
            try:
                output_path.unlink()
            except Exception:
                pass
    except Exception:
        pass

    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).first()
    if not job:
        job = TranscodeJob(file_path=job_key, status='processing', progress=0, output_path=None, duration=0, created_at=time.time())
        db.add(job)
    else:
        job.status = 'processing'
        job.progress = 0
        job.output_path = None
        job.created_at = time.time()
    db.commit()
    return job


def transcode_video_with_progress(input_path: Path, output_path: Path, file_path: str, expected_source_signature: str | None = None):
    attempt = None
    try:
        with SessionLocal() as session:
            attempt = claim_transcode_job(session, job_key=file_path, output_path=output_path)
        if attempt is None:
            return False

        info = get_video_info(input_path)
        duration = info['duration']
        ensure_data_capacity(_estimated_mp4_output_bytes(input_path, duration))
        current_state = transcode_progress.get(file_path, {})
        transcode_progress[file_path] = {**current_state, 'progress': 0, 'status': 'processing', 'duration': duration}

        tmp_output_path = output_path.with_name(f'{output_path.stem}.{attempt.attempt_id}.{uuid4().hex}.part{output_path.suffix}')
        try:
            if tmp_output_path.exists():
                tmp_output_path.unlink()
        except Exception:
            pass

        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-nostats',
            '-loglevel',
            'error',
            '-y',
            '-i',
            str(input_path),
            '-c:v',
            'libx264',
            '-preset',
            'fast',
            '-crf',
            '23',
        ]
        if settings.TRANSCODE_RESOLUTION != 'source':
            cmd.extend(['-vf', f'scale=-2:{int(settings.TRANSCODE_RESOLUTION)}'])

        cmd.extend(['-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-progress', 'pipe:1', '-f', 'mp4', str(tmp_output_path)])

        tail = deque(maxlen=80)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        transcode_processes[file_path] = process
        last_heartbeat = time.time()
        if process.stdout:
            for line in process.stdout:
                if file_path in transcode_cancel_requested or not owns_transcode_claim(attempt):
                    process.terminate()
                    break
                last_heartbeat = maybe_renew_transcode_claim(attempt, last_heartbeat)
                line = (line or '').strip()
                if line:
                    tail.append(line)
                if line.startswith('out_time_ms='):
                    try:
                        ensure_data_capacity()
                    except HTTPException:
                        process.terminate()
                        raise
                    try:
                        time_ms = int(line.split('=')[1].strip())
                        if duration > 0:
                            progress = min(99, (time_ms / 1_000_000 / duration) * 100)
                            transcode_progress[file_path]['progress'] = round(progress, 1)
                    except Exception:
                        pass
        returncode = process.wait()

        if returncode == 0 and tmp_output_path.exists() and tmp_output_path.stat().st_size > 0:
            with transcode_publish_guard(file_path, attempt):
                if file_path in transcode_cancel_requested or not owns_transcode_claim(attempt):
                    raise RuntimeError('transcode attempt was cancelled')
                if expected_source_signature and source_signature(input_path) != expected_source_signature:
                    raise RuntimeError('source generation changed before publish')
                tmp_output_path.replace(output_path)
                tmp_output_path = None
            return mark_transcode_complete(attempt, output_path=output_path, duration=duration)

        try:
            if tmp_output_path.exists() and tmp_output_path.is_file():
                tmp_output_path.unlink()
        except Exception:
            pass

        err_tail = '\n'.join(list(tail)[-20:]) if tail else ''
        mark_transcode_error(attempt, error=err_tail or f'ffmpeg rc={returncode}', duration=duration)
        return False
    except Exception as exc:
        if attempt is not None:
            mark_transcode_error(attempt, error=str(exc))
        else:
            transcode_progress[file_path] = {'progress': 0, 'status': 'error', 'error': str(exc), 'completed_at': time.time()}
        return False
    finally:
        if 'tmp_output_path' in locals() and tmp_output_path is not None:
            try:
                tmp_output_path.unlink(missing_ok=True)
            except OSError:
                pass
        if attempt is not None:
            release_transcode_claim(attempt)


def ensure_transcode_running(db: Session, *, job_key: str, input_path: Path, output_path: Path) -> bool:
    restore_transcode_identity_for_authorized_source(job_key)
    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).first()
    force_restart = False

    if _is_nonempty_file(output_path):
        if not job:
            job = TranscodeJob(
                file_path=job_key,
                status='complete',
                progress=100,
                output_path=str(output_path),
                duration=0,
                created_at=time.time(),
                last_accessed=time.time(),
            )
            db.add(job)
            db.commit()
            enforce_transcode_cache_budget(db)
        elif job.status != 'complete' and not transcode_claim_is_active(job_key):
            job.status = 'complete'
            job.output_path = str(output_path)
            job.progress = 100
            job.last_accessed = time.time()
            db.commit()
            enforce_transcode_cache_budget(db)
        return True

    if job:
        if job.status == 'complete':
            if not job.output_path or not _is_nonempty_file(Path(job.output_path)):
                force_restart = True
        elif job.status in {'error', 'pending'}:
            force_restart = True
        elif job.status == 'processing':
            if transcode_claim_is_active(job_key):
                return False
            force_restart = True

    if not job or force_restart:
        ensure_data_capacity(_estimated_mp4_output_bytes(input_path))
        if force_restart:
            transcode_progress.pop(job_key, None)
        _start_or_restart_transcode_job(db, job_key, output_path)

    inflight = transcode_progress.get(job_key) or {}
    if inflight.get('status') != 'processing':
        expected_generation = source_signature(input_path)
        executor.submit(transcode_video_with_progress, input_path, output_path, job_key, expected_generation)

    return False


def stream_file_response(full_path: Path, transcode_job_key: str, db: Session):
    if not full_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    if not is_video(full_path):
        return FileResponse(full_path, filename=full_path.name)
    if not needs_transcode(full_path):
        return FileResponse(full_path, media_type='video/mp4')

    preview_job_key = mp4_job_key(transcode_job_key)
    transcode_path = transcode_cache_path_for_identity(preview_job_key)
    _adopt_legacy_mp4_artifact(db, legacy_job_key=transcode_job_key, artifact_job_key=preview_job_key, artifact_path=transcode_path)
    if ensure_transcode_running(db, job_key=preview_job_key, input_path=full_path, output_path=transcode_path):
        touch_transcode_access(preview_job_key)
        return FileResponse(transcode_path, media_type='video/mp4')
    return {'status': 'transcoding', 'message': 'Video is being converted...'}
