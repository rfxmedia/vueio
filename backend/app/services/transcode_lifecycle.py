from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TranscodeJob
from app.runtime_state import transcode_cancel_requested, transcode_processes, transcode_progress
from app.services.media import get_file_hash

settings = get_settings()

MP4_PREVIEW_PROFILE_VERSION = 'mp4-preview-v2-h264-aac'
TRANSCODE_LEASE_SECONDS = 2 * 60
TRANSCODE_HEARTBEAT_SECONDS = 30
TRANSCODE_ACCESS_TOUCH_INTERVAL_SECONDS = 60
TRANSCODE_SERVE_GRACE_SECONDS = 60
_transcode_access_touches: dict[str, float] = {}
_transcode_access_touches_lock = threading.Lock()


@dataclass(frozen=True)
class TranscodeAttempt:
    job_key: str
    attempt_id: str
    lock_path: Path


def artifact_job_key(source_identity: str, artifact_kind: str, profile_version: str) -> str:
    source = str(source_identity or '').strip()
    if not source:
        raise ValueError('source_identity is required')
    kind = str(artifact_kind or '').strip().lower()
    profile = str(profile_version or '').strip()
    if not kind or not profile:
        raise ValueError('artifact kind and profile are required')
    return f'artifact:{kind}:{profile}:{source}'


def mp4_job_key(source_identity: str) -> str:
    return artifact_job_key(source_identity, 'mp4', MP4_PREVIEW_PROFILE_VERSION)


def transcode_lock_dir() -> Path:
    path = settings.transcode_dir / '.locks'
    path.mkdir(parents=True, exist_ok=True)
    return path


def transcode_lock_path(job_key: str) -> Path:
    return transcode_lock_dir() / f'{get_file_hash(job_key)}.lock'


def transcode_cancel_path(job_key: str) -> Path:
    return transcode_lock_dir() / f'{get_file_hash(job_key)}.cancel'


def transcode_publish_lock_path(job_key: str) -> Path:
    return transcode_lock_dir() / f'{get_file_hash(job_key)}.publish.lock'


def _read_lock(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _lock_is_live(path: Path, now: float | None = None) -> bool:
    data = _read_lock(path)
    if not data:
        return False
    return float(data.get('expires_at') or 0) > (now or time.time())


def _local_process_is_live(job_key: str) -> bool:
    process = transcode_processes.get(job_key)
    if process is None:
        return False
    try:
        return process.poll() is None
    except Exception:
        return False


def _has_local_live_owner(job_key: str) -> bool:
    return _local_process_is_live(job_key)


def transcode_claim_is_active(job_key: str, now: float | None = None) -> bool:
    lock_path = transcode_lock_path(job_key)
    data = _read_lock(lock_path)
    if not data or data.get('job_key') != job_key:
        return False
    return _lock_is_live(lock_path, now) or _has_local_live_owner(job_key)


def transcode_identity_is_cancelled(job_key: str) -> bool:
    return job_key in transcode_cancel_requested or transcode_cancel_path(job_key).exists()


def restore_transcode_identity_for_authorized_source(job_key: str) -> bool:
    """Clear a durable purge tombstone after the caller has re-authorized the source."""
    if not transcode_identity_is_cancelled(job_key):
        return True
    if transcode_claim_is_active(job_key):
        return False
    try:
        transcode_cancel_path(job_key).unlink(missing_ok=True)
    except OSError:
        return False
    transcode_cancel_requested.discard(job_key)
    return True


def tombstone_transcode_identity(job_key: str, *, reason: str = 'cancelled') -> None:
    transcode_cancel_requested.add(job_key)
    payload = {
        'job_key': job_key,
        'reason': reason,
        'pid': os.getpid(),
        'created_at': time.time(),
    }
    cancel_path = transcode_cancel_path(job_key)
    tmp_path = cancel_path.with_name(f'{cancel_path.name}.{uuid.uuid4().hex}.tmp')
    try:
        tmp_path.write_text(json.dumps(payload), encoding='utf-8')
        tmp_path.replace(cancel_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def transcode_publish_guard(job_key: str, attempt: TranscodeAttempt | None = None, *, allow_cancelled: bool = False):
    try:
        import fcntl
    except Exception:
        fcntl = None

    lock_path = transcode_publish_lock_path(job_key)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, 'a+', encoding='utf-8') as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if not allow_cancelled and transcode_identity_is_cancelled(job_key):
                raise RuntimeError('transcode identity was cancelled')
            if attempt is not None and not owns_transcode_claim(attempt):
                raise RuntimeError('transcode claim is no longer owned')
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def active_transcode_locks() -> list[Path]:
    lock_dir = transcode_lock_dir()
    return [path for path in lock_dir.glob('*.lock') if _lock_is_live(path)]


def claim_transcode_job(db: Session, *, job_key: str, output_path: Path | None = None) -> TranscodeAttempt | None:
    now = time.time()
    lock_path = transcode_lock_path(job_key)
    attempt_id = uuid.uuid4().hex
    payload = {
        'job_key': job_key,
        'attempt_id': attempt_id,
        'pid': os.getpid(),
        'created_at': now,
        'expires_at': now + TRANSCODE_LEASE_SECONDS,
    }
    # Serialize stale-lease takeover with renewal and release. Without this
    # guard, an expired owner's late heartbeat or cleanup could replace/remove
    # the next worker's newly-created lease.
    with transcode_publish_guard(job_key, allow_cancelled=True):
        if transcode_identity_is_cancelled(job_key):
            return None
        lock_data = _read_lock(lock_path) if lock_path.exists() else None
        if lock_path.exists() and (
            not lock_data
            or (
                lock_data.get('job_key') == job_key
                and not _lock_is_live(lock_path, now)
                and not _has_local_live_owner(job_key)
            )
        ):
            try:
                lock_path.unlink()
            except OSError:
                pass
        try:
            fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return None
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)

    try:
        job = db.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).first()
        if not job:
            job = TranscodeJob(file_path=job_key, status='processing', progress=0, output_path=None, duration=0, created_at=now)
            db.add(job)
        else:
            job.status = 'processing'
            job.progress = 0
            job.output_path = None
            job.created_at = now
        if output_path is not None:
            job.output_path = str(output_path)
        db.commit()
        transcode_cancel_requested.discard(job_key)
        transcode_progress[job_key] = {'progress': 0, 'status': 'processing', 'attempt_id': attempt_id}
        return TranscodeAttempt(job_key=job_key, attempt_id=attempt_id, lock_path=lock_path)
    except Exception:
        release_transcode_claim(TranscodeAttempt(job_key=job_key, attempt_id=attempt_id, lock_path=lock_path))
        raise


def owns_transcode_claim(attempt: TranscodeAttempt) -> bool:
    data = _read_lock(attempt.lock_path)
    return bool(data and data.get('attempt_id') == attempt.attempt_id and data.get('job_key') == attempt.job_key)


def renew_transcode_claim(attempt: TranscodeAttempt) -> bool:
    tmp_path = attempt.lock_path.with_name(f'{attempt.lock_path.name}.{attempt.attempt_id}.tmp')
    with transcode_publish_guard(attempt.job_key, allow_cancelled=True):
        if transcode_identity_is_cancelled(attempt.job_key):
            return False
        data = _read_lock(attempt.lock_path)
        if not data or data.get('attempt_id') != attempt.attempt_id or data.get('job_key') != attempt.job_key:
            return False
        now = time.time()
        data['heartbeat_at'] = now
        data['expires_at'] = now + TRANSCODE_LEASE_SECONDS
        try:
            tmp_path.write_text(json.dumps(data), encoding='utf-8')
            tmp_path.replace(attempt.lock_path)
            state = transcode_progress.get(attempt.job_key)
            if state and state.get('attempt_id') == attempt.attempt_id:
                state['heartbeat_at'] = now
            return True
        except OSError:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False


def maybe_renew_transcode_claim(attempt: TranscodeAttempt, last_heartbeat: float) -> float:
    now = time.time()
    if now - last_heartbeat < TRANSCODE_HEARTBEAT_SECONDS:
        return last_heartbeat
    return now if renew_transcode_claim(attempt) else last_heartbeat


def release_transcode_claim(attempt: TranscodeAttempt) -> None:
    with transcode_publish_guard(attempt.job_key, allow_cancelled=True):
        if owns_transcode_claim(attempt):
            try:
                attempt.lock_path.unlink()
            except OSError:
                pass
    transcode_processes.pop(attempt.job_key, None)
    transcode_cancel_requested.discard(attempt.job_key)


def transcode_artifact_job_keys(source_identity: str) -> list[str]:
    from app.services.hls_streaming import hls_job_key

    return [mp4_job_key(source_identity), hls_job_key(source_identity)]


def all_transcode_identities_for_source(source_identity: str) -> list[str]:
    return [source_identity, *transcode_artifact_job_keys(source_identity)]


def _remove_transcode_artifact_files(job_key: str) -> None:
    from app.services.media_resolution import hls_package_dir_for_identity, transcode_cache_path_for_identity

    try:
        transcode_cache_path_for_identity(job_key).unlink(missing_ok=True)
    except OSError:
        pass

    hls_dir = hls_package_dir_for_identity(job_key)
    hls_parent = hls_dir.parent
    hls_name = hls_dir.name
    shutil.rmtree(hls_dir, ignore_errors=True)
    for path in hls_parent.glob(f'{hls_name}.*'):
        if path == transcode_publish_lock_path(job_key) or path == transcode_cancel_path(job_key):
            continue
        if path.name.startswith(f'{hls_name}.') and path.name.endswith(('.pkg', '.part', '.migrate', '.old', '.tmp')):
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
    try:
        hls_dir.with_name(f'{hls_name}.current.json').unlink(missing_ok=True)
    except OSError:
        pass
    for index_path in hls_parent.glob('*.hls.json'):
        try:
            data = json.loads(index_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if data.get('package_job_key') == job_key or str(data.get('package_dir') or '').startswith(f'{hls_name}.'):
            try:
                index_path.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        transcode_lock_path(job_key).unlink(missing_ok=True)
    except OSError:
        pass


def purge_transcode_identity(job_key: str, *, db: Session | None = None) -> None:
    tombstone_transcode_identity(job_key, reason='purged')
    process = transcode_processes.get(job_key)
    if process is not None:
        live = False
        try:
            if process.poll() is None:
                live = True
                process.terminate()
        except Exception:
            pass
        if live:
            try:
                process.wait(timeout=2.0)
            except Exception:
                try:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=1.0)
                except Exception:
                    pass

    with transcode_publish_guard(job_key, allow_cancelled=True):
        _remove_transcode_artifact_files(job_key)
    transcode_progress.pop(job_key, None)
    transcode_processes.pop(job_key, None)
    with _transcode_access_touches_lock:
        _transcode_access_touches.pop(job_key, None)
    if db is not None:
        db.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).delete(synchronize_session=False)
    else:
        with SessionLocalForTranscode() as session:
            session.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).delete(synchronize_session=False)
            session.commit()


def touch_transcode_access(job_key: str) -> None:
    """Record real artifact use without writing once per HLS segment."""
    now = time.time()
    with _transcode_access_touches_lock:
        previous = _transcode_access_touches.get(job_key)
        if previous is not None and now - previous < TRANSCODE_ACCESS_TOUCH_INTERVAL_SECONDS:
            return
        _transcode_access_touches[job_key] = now
    try:
        with SessionLocalForTranscode() as session:
            job = session.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).first()
            if job is None or job.status != 'complete':
                with _transcode_access_touches_lock:
                    if _transcode_access_touches.get(job_key) == now:
                        _transcode_access_touches.pop(job_key, None)
                return
            job.last_accessed = now
            session.add(job)
            session.commit()
    except Exception:
        with _transcode_access_touches_lock:
            if _transcode_access_touches.get(job_key) == now:
                _transcode_access_touches.pop(job_key, None)


def _contained_transcode_output(job: TranscodeJob) -> Path | None:
    if not job.output_path:
        return None
    try:
        root = settings.transcode_dir.resolve()
        output = Path(job.output_path).resolve()
        output.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return output.parent if output.suffix.lower() == '.m3u8' else output


def _transcode_artifact_paths(job: TranscodeJob) -> set[Path]:
    """Return every cache path owned by one persisted transcode job."""
    from app.services.media_resolution import hls_package_dir_for_identity, transcode_cache_path_for_identity

    output = _contained_transcode_output(job)
    if output is None:
        return set()
    paths = {output}
    output_path = Path(job.output_path)
    if output_path.suffix.lower() != '.m3u8':
        canonical = transcode_cache_path_for_identity(job.file_path)
        try:
            canonical.resolve().relative_to(settings.transcode_dir.resolve())
            paths.add(canonical.resolve())
        except (OSError, RuntimeError, ValueError):
            pass
        return paths

    hls_base = hls_package_dir_for_identity(job.file_path)
    paths.add(hls_base)
    paths.add(hls_base.with_name(f'{hls_base.name}.current.json'))
    for candidate in hls_base.parent.glob(f'{hls_base.name}.*'):
        if candidate.name.startswith(f'{hls_base.name}.') and candidate.name.endswith(
            ('.pkg', '.part', '.migrate', '.old', '.tmp')
        ):
            paths.add(candidate)
    for index_path in hls_base.parent.glob('*.hls.json'):
        try:
            data = json.loads(index_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if data.get('package_job_key') == job.file_path or str(data.get('package_dir') or '').startswith(f'{hls_base.name}.'):
            paths.add(index_path)
    return paths


def _regular_file_bytes(path: Path) -> int:
    try:
        if path.is_file() and not path.is_symlink():
            return path.stat().st_size
        if not path.is_dir() or path.is_symlink():
            return 0
    except OSError:
        return 0
    total = 0
    for child in path.rglob('*'):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _tracked_transcode_cache_bytes(jobs: list[TranscodeJob]) -> int:
    """Measure only artifacts owned by transcode jobs.

    Thumbnails and other rebuildable caches live beside the transcode cache but
    have different ownership and lifecycle rules. Counting them here would make
    a transcode-only limit impossible to enforce safely.
    """
    total = 0
    seen: set[Path] = set()
    for job in jobs:
        for artifact in _transcode_artifact_paths(job):
            if artifact in seen:
                continue
            seen.add(artifact)
            total += _regular_file_bytes(artifact)
    return total


def transcode_cache_bytes(db: Session | None = None) -> int:
    owns_session = db is None
    session = db
    if session is None:
        from app.db import SessionLocal

        session = SessionLocal()
    try:
        return _tracked_transcode_cache_bytes(session.query(TranscodeJob).all())
    finally:
        if owns_session:
            session.close()


def enforce_transcode_cache_budget(db: Session | None = None) -> dict:
    """Evict only completed, reproducible artifacts in true access order."""
    budget = int(settings.TRANSCODE_CACHE_MAX_BYTES)
    owns_session = db is None
    session = db
    if session is None:
        from app.db import SessionLocal

        session = SessionLocal()
    try:
        all_jobs = session.query(TranscodeJob).all()
        current_bytes = _tracked_transcode_cache_bytes(all_jobs)
        result = {
            'budget_bytes': budget,
            'before_bytes': current_bytes,
            'after_bytes': current_bytes,
            'evicted_jobs': 0,
            'evicted_bytes': 0,
        }
        if budget <= 0 or current_bytes <= budget:
            return result

        jobs = [job for job in all_jobs if job.status == 'complete']
        jobs.sort(key=lambda job: (float(job.last_accessed or job.created_at or 0), int(job.id or 0)))
        now = time.time()
        for job in jobs:
            if current_bytes <= budget:
                break
            job_key = job.file_path
            if transcode_claim_is_active(job_key):
                continue
            with _transcode_access_touches_lock:
                recent_process_access = _transcode_access_touches.get(job_key, 0)
            last_accessed = max(float(job.last_accessed or job.created_at or 0), recent_process_access)
            if now - last_accessed < TRANSCODE_SERVE_GRACE_SECONDS:
                continue
            with transcode_publish_guard(job_key):
                # A serve or another evictor may have updated/deleted this row
                # while we waited for the artifact lock. Re-read both the
                # durable access time and this process's coalesced touch before
                # removing anything.
                fresh_job = (
                    session.query(TranscodeJob)
                    .filter(TranscodeJob.id == job.id)
                    .populate_existing()
                    .first()
                )
                if fresh_job is None or fresh_job.status != 'complete':
                    continue
                if transcode_claim_is_active(job_key):
                    continue
                with _transcode_access_touches_lock:
                    recent_process_access = _transcode_access_touches.get(job_key, 0)
                last_accessed = max(
                    float(fresh_job.last_accessed or fresh_job.created_at or 0),
                    recent_process_access,
                )
                if time.time() - last_accessed < TRANSCODE_SERVE_GRACE_SECONDS:
                    continue
                artifact_paths = _transcode_artifact_paths(fresh_job)
                if not artifact_paths:
                    continue
                artifact_bytes = sum(_regular_file_bytes(path) for path in artifact_paths)
                _remove_transcode_artifact_files(job_key)
                session.delete(fresh_job)
                session.commit()
            with _transcode_access_touches_lock:
                _transcode_access_touches.pop(job_key, None)
            current_bytes = max(0, current_bytes - artifact_bytes)
            result['evicted_jobs'] += 1
            result['evicted_bytes'] += artifact_bytes
        result['after_bytes'] = _tracked_transcode_cache_bytes(session.query(TranscodeJob).all())
        return result
    finally:
        if owns_session:
            session.close()


def mark_transcode_complete(attempt: TranscodeAttempt, *, output_path: Path, progress: float = 100, duration: float = 0) -> bool:
    if transcode_identity_is_cancelled(attempt.job_key) or not owns_transcode_claim(attempt):
        return False
    transcode_progress[attempt.job_key] = {'progress': progress, 'status': 'complete', 'completed_at': time.time(), 'attempt_id': attempt.attempt_id}
    with SessionLocalForTranscode() as session:
        job = session.query(TranscodeJob).filter(TranscodeJob.file_path == attempt.job_key).first()
        if job:
            job.status = 'complete'
            job.output_path = str(output_path)
            job.progress = progress
            job.duration = duration or job.duration or 0
            job.last_accessed = time.time()
            session.commit()
    enforce_transcode_cache_budget()
    return True


def mark_transcode_error(attempt: TranscodeAttempt, *, error: str, duration: float = 0) -> None:
    if transcode_identity_is_cancelled(attempt.job_key) or not owns_transcode_claim(attempt):
        return
    transcode_progress[attempt.job_key] = {
        'progress': 0,
        'status': 'error',
        'error': error,
        'completed_at': time.time(),
        'attempt_id': attempt.attempt_id,
    }
    with SessionLocalForTranscode() as session:
        job = session.query(TranscodeJob).filter(TranscodeJob.file_path == attempt.job_key).first()
        if job:
            job.status = 'error'
            job.output_path = None
            job.progress = 0
            job.duration = duration or job.duration or 0
            session.commit()


class SessionLocalForTranscode:
    def __enter__(self):
        from app.db import SessionLocal

        self.session = SessionLocal()
        return self.session

    def __exit__(self, exc_type, exc, tb):
        self.session.close()


def cancel_all_transcodes(*, wait_seconds: float = 2.0) -> int:
    keys = set(transcode_processes) | {key for key, state in transcode_progress.items() if state.get('status') == 'processing'}
    for lock_path in active_transcode_locks():
        data = _read_lock(lock_path) or {}
        if data.get('job_key'):
            keys.add(str(data['job_key']))
    for key in keys:
        transcode_cancel_requested.add(key)

    processes = list(transcode_processes.items())
    for _key, process in processes:
        try:
            if process.poll() is None:
                process.terminate()
        except Exception:
            pass

    deadline = time.time() + max(0.0, wait_seconds)
    for _key, process in processes:
        remaining = max(0.0, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except Exception:
            try:
                if process.poll() is None:
                    process.kill()
            except Exception:
                pass

    for lock_path in transcode_lock_dir().glob('*.lock'):
        try:
            lock_path.unlink()
        except OSError:
            pass
    transcode_processes.clear()
    return len(keys)


def cleanup_transcode_runtime_state() -> None:
    transcode_progress.clear()
    transcode_cancel_requested.clear()
    transcode_processes.clear()
