from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
import zipfile
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, List

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import PackageJob
from app.services.storage_capacity import ensure_data_capacity


logger = logging.getLogger('vueio.package_jobs')
_PACKAGE_BUILD_LOCK = threading.Lock()
_PACKAGE_BUILD_ACTIVE = 0
_PACKAGE_JOB_TTL_SECONDS = 60 * 60 * 6
_ZIP_TEMP_PREFIXES = ('vueio_', 'vueio_job_')


@dataclass(frozen=True)
class ZipPreflight:
    entries: list['ZipEntry']
    total_bytes: int
    file_count: int
    largest_file_bytes: int


@dataclass
class ZipDiscoveryBudget:
    max_bytes: int
    max_files: int
    max_depth: int
    max_roots: int
    total_bytes: int = 0
    file_count: int = 0
    requested_roots: int = 0

    @classmethod
    def from_settings(cls) -> 'ZipDiscoveryBudget':
        settings = get_settings()
        return cls(
            max_bytes=int(getattr(settings, 'PACKAGE_SYNC_MAX_BYTES', 0) or 0),
            max_files=int(getattr(settings, 'PACKAGE_SYNC_MAX_FILES', 0) or 0),
            max_depth=max(0, int(getattr(settings, 'PACKAGE_SYNC_MAX_DEPTH', 64) or 0)),
            max_roots=int(getattr(settings, 'PACKAGE_SYNC_MAX_ROOTS', 0) or 0),
        )

    @property
    def remaining_files(self) -> int:
        if self.max_files <= 0:
            return 0
        return max(0, self.max_files - self.file_count)

    def charge_requested_root(self, count: int = 1) -> None:
        self.requested_roots += max(0, int(count or 0))
        if self.requested_roots > self.max_roots:
            _raise_zip_root_limit(self.requested_roots, self.max_roots)

    def check_depth(self, depth: int) -> None:
        if depth > self.max_depth:
            _raise_zip_depth_limit(self.max_depth)

    def charge_file(self, size: int) -> None:
        self.total_bytes += max(0, int(size or 0))
        self.file_count += 1
        _check_discovery_limits(self.total_bytes, self.file_count, budget=self)


@dataclass(frozen=True)
class ZipFileIdentity:
    st_dev: int
    st_ino: int
    st_size: int
    st_mtime_ns: int


@dataclass(frozen=True)
class ZipEntry:
    path: Path
    arcname: str
    identity: ZipFileIdentity | None = None

    def __iter__(self) -> Iterator[object]:
        yield self.path
        yield self.arcname


def clean_zip_arcname(desired: str) -> str:
    normalized = str(desired or '').replace('\\', '/').strip().strip('/')
    if not normalized:
        return 'file'
    parts = []
    for part in normalized.split('/'):
        part = part.strip()
        if not part or part in {'.', '..'}:
            continue
        parts.append(part)
    return str(PurePosixPath(*parts)) if parts else 'file'


def unique_arcname(desired: str, used: set[str]) -> str:
    if desired not in used:
        used.add(desired)
        return desired
    stem, dot, ext = desired.rpartition('.')
    if dot == '':
        stem, ext = desired, ''
    else:
        ext = f'.{ext}'
    index = 2
    while True:
        candidate = f'{stem} ({index}){ext}'
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def _arc_depth_offset(arc_root: str) -> int:
    try:
        return max(0, len(PurePosixPath(clean_zip_arcname(arc_root)).parts) - 1)
    except Exception:
        return 0


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def path_within_physical_root(path: Path, physical_root: Path) -> bool:
    try:
        resolved_path = path.resolve(strict=False)
        resolved_root = physical_root.resolve(strict=False)
    except Exception:
        return False
    return _is_relative_to(resolved_path, resolved_root)


def _identity_from_stat(st: os.stat_result) -> ZipFileIdentity:
    return ZipFileIdentity(
        st_dev=st.st_dev,
        st_ino=st.st_ino,
        st_size=st.st_size,
        st_mtime_ns=st.st_mtime_ns,
    )


def _lstat_regular_file(path: Path) -> os.stat_result | None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return None
    return st


def _lstat_directory(path: Path) -> os.stat_result | None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return None
    return st


def _raise_zip_limit(total_bytes: int, file_count: int) -> None:
    settings = get_settings()
    raise HTTPException(
        status_code=413,
        detail=(
            'This package is too large to build inline. '
            f'Limit is {_format_bytes(settings.PACKAGE_SYNC_MAX_BYTES)} or '
            f'{settings.PACKAGE_SYNC_MAX_FILES} files; request contains at least '
            f'{_format_bytes(total_bytes)} across {file_count} files. '
            'Download files individually, request a smaller folder, or use background packaging when available.'
        ),
    )


def _raise_zip_depth_limit(max_depth: int) -> None:
    raise HTTPException(
        status_code=413,
        detail=f'This package is too deeply nested to build inline. Limit is {max_depth} folder levels.',
    )


def _raise_zip_root_limit(root_count: int, max_roots: int) -> None:
    raise HTTPException(
        status_code=413,
        detail=(
            'This package has too many requested roots to build inline. '
            f'Limit is {max_roots} paths; request contains at least {root_count} paths.'
        ),
    )


def _check_discovery_limits(total_bytes: int, file_count: int, *, budget: ZipDiscoveryBudget | None = None) -> None:
    settings = get_settings()
    max_files = budget.max_files if budget is not None else settings.PACKAGE_SYNC_MAX_FILES
    max_bytes = budget.max_bytes if budget is not None else settings.PACKAGE_SYNC_MAX_BYTES
    bytes_disabled = max_bytes <= 0 and file_count > 0
    if file_count > max_files or bytes_disabled or total_bytes > max_bytes:
        _raise_zip_limit(total_bytes, file_count)


def new_zip_discovery_budget() -> ZipDiscoveryBudget:
    return ZipDiscoveryBudget.from_settings()


def collect_boundary_zip_entries(
    source_path: Path,
    arc_root: str | None = None,
    *,
    physical_root: Path,
    budget: ZipDiscoveryBudget | None = None,
    charge_root: bool = True,
    discovered_identities: set[ZipFileIdentity] | None = None,
    excluded_paths: set[Path] | None = None,
) -> list[ZipEntry]:
    discovery_budget = budget or new_zip_discovery_budget()
    if charge_root:
        discovery_budget.charge_requested_root()
    resolved_boundary = physical_root.resolve(strict=False)
    try:
        resolved_source = source_path.resolve(strict=False)
    except Exception as exc:
        raise HTTPException(status_code=403, detail='Access denied - path outside allowed folder') from exc
    if not _is_relative_to(resolved_source, resolved_boundary):
        raise HTTPException(status_code=403, detail='Access denied - path outside allowed folder')
    resolved_exclusions = excluded_paths or set()

    arc_base = clean_zip_arcname(arc_root or source_path.name or 'file')
    arc_depth_offset = _arc_depth_offset(arc_base)
    source_file_stat = _lstat_regular_file(source_path)
    if source_file_stat:
        if resolved_source in resolved_exclusions:
            return []
        if not path_within_physical_root(source_path, resolved_boundary):
            return []
        identity = _identity_from_stat(source_file_stat)
        if discovered_identities is not None:
            if identity in discovered_identities:
                return []
            discovered_identities.add(identity)
        discovery_budget.check_depth(arc_depth_offset)
        discovery_budget.charge_file(source_file_stat.st_size)
        return [ZipEntry(source_path, arc_base, identity)]
    if not _lstat_directory(source_path):
        return []

    entries: list[ZipEntry] = []
    stack: list[tuple[Path, int]] = [(source_path, 0)]
    while stack:
        current, depth = stack.pop()
        discovery_budget.check_depth(arc_depth_offset + depth)
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            continue
        for child in children:
            child_depth = depth + 1
            discovery_budget.check_depth(arc_depth_offset + child_depth)
            try:
                child_stat = os.lstat(child)
            except OSError:
                continue
            if stat.S_ISLNK(child_stat.st_mode):
                continue
            if stat.S_ISDIR(child_stat.st_mode):
                if path_within_physical_root(child, resolved_boundary):
                    stack.append((child, child_depth))
                continue
            if not stat.S_ISREG(child_stat.st_mode):
                continue
            if not path_within_physical_root(child, resolved_boundary):
                continue
            try:
                if child.resolve(strict=False) in resolved_exclusions:
                    continue
            except OSError:
                continue
            identity = _identity_from_stat(child_stat)
            if discovered_identities is not None:
                if identity in discovered_identities:
                    continue
                discovered_identities.add(identity)
            discovery_budget.charge_file(child_stat.st_size)
            rel = child.relative_to(source_path).as_posix()
            entries.append(ZipEntry(
                child,
                str(PurePosixPath(arc_base) / PurePosixPath(rel)),
                identity,
            ))
    return entries


def _format_bytes(value: int) -> str:
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f'{size:.1f} {unit}' if unit != 'B' else f'{int(size)} B'
        size /= 1024
    return f'{value} B'


def _coerce_zip_entry(entry: ZipEntry | tuple[Path, str]) -> ZipEntry | None:
    if isinstance(entry, ZipEntry):
        path = entry.path
        arcname = entry.arcname
        expected = entry.identity
    else:
        path, arcname = entry
        expected = None
    stat_result = _lstat_regular_file(path)
    if stat_result is None:
        if expected is not None:
            raise HTTPException(status_code=403, detail='Access denied - file changed while preparing archive')
        return None
    identity = _identity_from_stat(stat_result)
    if expected is not None and identity != expected:
        raise HTTPException(status_code=403, detail='Access denied - file changed while preparing archive')
    return ZipEntry(path, arcname, identity)


def preflight_zip_entries(entries: Iterable[ZipEntry | tuple[Path, str]]) -> ZipPreflight:
    total_bytes = 0
    file_count = 0
    largest_file_bytes = 0
    valid_entries: list[ZipEntry] = []

    for raw_entry in entries:
        entry = _coerce_zip_entry(raw_entry)
        if entry is None or entry.identity is None:
            continue
        size = entry.identity.st_size
        total_bytes += size
        file_count += 1
        largest_file_bytes = max(largest_file_bytes, size)
        valid_entries.append(entry)

        _check_discovery_limits(total_bytes, file_count)

    return ZipPreflight(
        entries=valid_entries,
        total_bytes=total_bytes,
        file_count=file_count,
        largest_file_bytes=largest_file_bytes,
    )


def _cleanup_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except FileNotFoundError:
        pass


def _package_artifact_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if (
        not path.name.startswith('vueio_job_')
        or path.suffix.lower() != '.zip'
        or not path_within_physical_root(path, get_settings().package_tmp_dir)
        or _lstat_regular_file(path) is None
    ):
        return None
    return path


def cleanup_orphaned_zip_temp_files(package_tmp_dir: Path | None = None) -> int:
    """Remove stale Vueio-owned ZIP temp files left behind by a prior process."""
    root = package_tmp_dir or get_settings().package_tmp_dir
    cutoff = time.time() - _PACKAGE_JOB_TTL_SECONDS
    try:
        children = list(root.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return 0
    except OSError:
        return 0

    removed = 0
    for path in children:
        name = path.name
        if not name.endswith('.zip') or not name.startswith(_ZIP_TEMP_PREFIXES):
            continue
        try:
            path_stat = os.lstat(path)
            if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
                continue
            if path_stat.st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
        except (FileNotFoundError, OSError):
            continue
    return removed


def _normalize_zip_filename(zip_filename: str | None) -> str:
    filename = (zip_filename or 'download.zip').strip() or 'download.zip'
    if not filename.lower().endswith('.zip'):
        filename += '.zip'
    return filename


def _estimated_zip_output_bytes(preflight: ZipPreflight) -> int:
    # Stored ZIPs contain the source bytes plus small per-entry headers. One KiB
    # per file is deliberately conservative without introducing a quota model.
    return preflight.total_bytes + max(1024 * 1024, preflight.file_count * 1024)


def _package_job_payload(job: PackageJob) -> dict:
    return {
        'id': job.id,
        'filename': job.filename,
        'status': job.status,
        'progress': job.progress,
        'total_bytes': job.total_bytes,
        'packaged_bytes': job.packaged_bytes,
        'file_count': job.file_count,
        'packaged_files': job.packaged_files,
        'message': job.message,
        'error': job.error,
        'created_at': job.created_at,
        'updated_at': job.updated_at,
    }


def get_zip_package_job_record(db: Session, job_id: str) -> PackageJob:
    job = db.get(PackageJob, job_id)
    if job is None or float(job.expires_at or 0) <= time.time():
        raise HTTPException(status_code=404, detail='Package job not found')
    return job


def _cleanup_old_package_jobs() -> None:
    now = time.time()
    db = SessionLocal()
    try:
        stale = db.query(PackageJob).filter(PackageJob.expires_at <= now).all()
        for job in stale:
            artifact = _package_artifact_path(job.artifact_path)
            if artifact is not None:
                _cleanup_file(artifact)
            db.delete(job)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception('Failed to clean expired package jobs')
    finally:
        db.close()


def recover_interrupted_package_jobs() -> int:
    """Fail jobs whose worker vanished during a process restart."""
    db = SessionLocal()
    try:
        jobs = db.query(PackageJob).filter(PackageJob.status.in_(('queued', 'packaging'))).all()
        now = time.time()
        for job in jobs:
            artifact = _package_artifact_path(job.artifact_path)
            if artifact is not None:
                _cleanup_file(artifact)
            job.status = 'failed'
            job.progress = 0
            job.message = 'Package preparation was interrupted'
            job.error = 'The server restarted while preparing this package. Please request it again.'
            job.artifact_path = None
            job.updated_at = now
            job.expires_at = now + _PACKAGE_JOB_TTL_SECONDS
        db.commit()
        return len(jobs)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _set_job(db: Session, job: PackageJob, *, commit: bool = True, **updates) -> None:
    now = time.time()
    for key, value in updates.items():
        setattr(job, key, value)
    job.updated_at = now
    job.expires_at = now + _PACKAGE_JOB_TTL_SECONDS
    db.add(job)
    if commit:
        db.commit()


def _zip_datetime(stat_result: os.stat_result) -> tuple[int, int, int, int, int, int]:
    timestamp = time.localtime(stat_result.st_mtime)[:6]
    if timestamp[0] < 1980:
        return (1980, 1, 1, 0, 0, 0)
    return timestamp


def _open_stable_file(entry: ZipEntry):
    if entry.identity is None:
        raise HTTPException(status_code=403, detail='Access denied - archive entry was not checked')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(entry.path, flags)
    except OSError as exc:
        raise HTTPException(status_code=403, detail='Access denied - file changed while preparing archive') from exc
    try:
        stat_result = os.fstat(fd)
        if not stat.S_ISREG(stat_result.st_mode) or _identity_from_stat(stat_result) != entry.identity:
            raise HTTPException(status_code=403, detail='Access denied - file changed while preparing archive')
        return os.fdopen(fd, 'rb'), stat_result
    except Exception:
        os.close(fd)
        raise


def _write_stored_zip_entry(
    zf: zipfile.ZipFile,
    entry: ZipEntry,
    arcname: str,
    *,
    db: Session | None = None,
    job: PackageJob | None = None,
    chunk_size: int = 1024 * 1024 * 4,
) -> None:
    src, stat_result = _open_stable_file(entry)
    info = zipfile.ZipInfo(arcname, _zip_datetime(stat_result))
    info.compress_type = zipfile.ZIP_STORED
    info.file_size = stat_result.st_size
    last_progress_commit = time.monotonic()
    with src, zf.open(info, 'w') as dest:
        while True:
            chunk = src.read(chunk_size)
            if not chunk:
                break
            dest.write(chunk)
            if db is not None and job is not None:
                packaged = min(job.total_bytes, job.packaged_bytes + len(chunk))
                progress = (packaged / job.total_bytes * 100) if job.total_bytes else 100.0
                _set_job(db, job, commit=False, packaged_bytes=packaged, progress=round(progress, 2))
                if time.monotonic() - last_progress_commit >= 1:
                    db.commit()
                    last_progress_commit = time.monotonic()


def _finish_zip_job(job_id: str, entries: list[ZipEntry]) -> None:
    settings = get_settings()
    settings.package_tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    db = SessionLocal()
    job = db.get(PackageJob, job_id)
    if job is None:
        db.close()
        return

    active_limit = max(1, int(getattr(settings, 'PACKAGE_SYNC_MAX_ACTIVE_BUILDS', 1) or 1))
    global _PACKAGE_BUILD_ACTIVE
    with _PACKAGE_BUILD_LOCK:
        if _PACKAGE_BUILD_ACTIVE >= active_limit:
            _set_job(
                db,
                job,
                status='failed',
                progress=0,
                message='Another package is already being prepared',
                error='Another package is already being prepared. Try again shortly.',
            )
            db.close()
            return
        _PACKAGE_BUILD_ACTIVE += 1

    used = set()
    try:
        ensure_data_capacity(job.total_bytes + max(1024 * 1024, job.file_count * 1024))
        tmp_file = tempfile.NamedTemporaryFile(prefix='vueio_job_', suffix='.zip', dir=settings.package_tmp_dir, delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()
        _set_job(db, job, status='packaging', message='Packaging files', artifact_path=str(tmp_path))
        with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            for entry in entries:
                _write_stored_zip_entry(
                    zf,
                    entry,
                    unique_arcname(clean_zip_arcname(entry.arcname), used),
                    db=db,
                    job=job,
                )
                _set_job(db, job, packaged_files=job.packaged_files + 1)
        _set_job(
            db,
            job,
            status='ready',
            progress=100.0,
            packaged_bytes=job.total_bytes,
            packaged_files=job.file_count,
            message='Ready to download',
            artifact_path=str(tmp_path),
        )
    except Exception as exc:
        db.rollback()
        job = db.get(PackageJob, job_id)
        if tmp_path is not None:
            _cleanup_file(tmp_path)
        if job is not None:
            _set_job(db, job, status='failed', message='Package failed', error=str(exc), artifact_path=None)
    finally:
        db.close()
        with _PACKAGE_BUILD_LOCK:
            _PACKAGE_BUILD_ACTIVE = max(0, _PACKAGE_BUILD_ACTIVE - 1)


def start_zip_package_job(
    entries: Iterable[ZipEntry | tuple[Path, str]],
    zip_filename: str | None = None,
    *,
    owner_type: str,
    owner_id: str,
    project_id: str | None = None,
    authorization: dict | None = None,
) -> dict:
    _cleanup_old_package_jobs()
    filename = _normalize_zip_filename(zip_filename)
    preflight = preflight_zip_entries(entries)
    if not preflight.entries:
        raise HTTPException(status_code=404, detail='No downloadable files found')
    ensure_data_capacity(_estimated_zip_output_bytes(preflight))

    now = time.time()
    job = PackageJob(
        id=uuid.uuid4().hex,
        kind='zip',
        filename=filename,
        status='queued',
        progress=0.0,
        total_bytes=preflight.total_bytes,
        packaged_bytes=0,
        file_count=preflight.file_count,
        packaged_files=0,
        message=f'Queued {preflight.file_count} files',
        owner_type=owner_type,
        owner_id=owner_id,
        project_id=project_id,
        authorization_json=json.dumps(authorization or {}, separators=(',', ':')),
        created_at=now,
        updated_at=now,
        expires_at=now + _PACKAGE_JOB_TTL_SECONDS,
    )
    db = SessionLocal()
    try:
        db.add(job)
        db.commit()
        payload = _package_job_payload(job)
    finally:
        db.close()

    thread = threading.Thread(target=_finish_zip_job, args=(job.id, list(preflight.entries)), daemon=True)
    try:
        thread.start()
    except Exception as exc:
        db = SessionLocal()
        try:
            failed_job = db.get(PackageJob, job.id)
            if failed_job is not None:
                _set_job(
                    db,
                    failed_job,
                    status='failed',
                    message='Package failed',
                    error=f'Unable to start package worker: {exc}',
                )
        finally:
            db.close()
        raise HTTPException(status_code=503, detail='Unable to start package preparation') from exc
    return payload


def get_zip_package_job(job_id: str, db: Session | None = None) -> dict:
    _cleanup_old_package_jobs()
    owns_db = db is None
    db = db or SessionLocal()
    try:
        return _package_job_payload(get_zip_package_job_record(db, job_id))
    finally:
        if owns_db:
            db.close()


def get_zip_package_job_download(
    job_id: str,
    *,
    db: Session | None = None,
) -> FileResponse:
    _cleanup_old_package_jobs()
    owns_db = db is None
    db = db or SessionLocal()
    try:
        job = get_zip_package_job_record(db, job_id)
        path = _package_artifact_path(job.artifact_path)
        if job.status != 'ready' or path is None:
            raise HTTPException(status_code=409, detail='Package is not ready yet')
        response = FileResponse(path, media_type='application/zip', filename=job.filename)
        response.headers['X-Vueio-Zip-Bytes'] = str(job.total_bytes)
        response.headers['X-Vueio-Zip-Files'] = str(job.file_count)
        response.headers['X-Vueio-Zip-Compression'] = 'stored'
        return response
    finally:
        if owns_db:
            db.close()


def _build_zip_response(entries: Iterable[ZipEntry | tuple[Path, str]], zip_filename: str, background_tasks: BackgroundTasks) -> FileResponse:
    zip_filename = _normalize_zip_filename(zip_filename)

    preflight = preflight_zip_entries(entries)
    if not preflight.entries:
        raise HTTPException(status_code=404, detail='No downloadable files found')
    ensure_data_capacity(_estimated_zip_output_bytes(preflight))
    settings = get_settings()
    settings.package_tmp_dir.mkdir(parents=True, exist_ok=True)

    tmp_file = tempfile.NamedTemporaryFile(prefix='vueio_', suffix='.zip', dir=settings.package_tmp_dir, delete=False)
    tmp_path = Path(tmp_file.name)
    tmp_file.close()

    active_limit = max(1, int(getattr(settings, 'PACKAGE_SYNC_MAX_ACTIVE_BUILDS', 1) or 1))
    # In-process guard for the current single-uvicorn deployment. If we later run
    # multiple backend processes, promote this same rule into the planned DB-backed
    # package job queue so every worker shares one global limit.
    global _PACKAGE_BUILD_ACTIVE
    with _PACKAGE_BUILD_LOCK:
        if _PACKAGE_BUILD_ACTIVE >= active_limit:
            _cleanup_file(tmp_path)
            raise HTTPException(
                status_code=429,
                detail='Another package is already being prepared. Try again shortly, download files individually, or request a smaller folder.',
            )
        _PACKAGE_BUILD_ACTIVE += 1

    used = set()
    try:
        with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            for entry in preflight.entries:
                _write_stored_zip_entry(zf, entry, unique_arcname(clean_zip_arcname(entry.arcname), used))
    except Exception:
        _cleanup_file(tmp_path)
        raise
    finally:
        with _PACKAGE_BUILD_LOCK:
            _PACKAGE_BUILD_ACTIVE = max(0, _PACKAGE_BUILD_ACTIVE - 1)

    background_tasks.add_task(_cleanup_file, tmp_path)
    response = FileResponse(tmp_path, media_type='application/zip', filename=zip_filename)
    response.headers['X-Vueio-Zip-Bytes'] = str(preflight.total_bytes)
    response.headers['X-Vueio-Zip-Files'] = str(preflight.file_count)
    response.headers['X-Vueio-Zip-Largest-File-Bytes'] = str(preflight.largest_file_bytes)
    response.headers['X-Vueio-Zip-Compression'] = 'stored'
    return response


def build_zip_entries(entries: Iterable[ZipEntry | tuple[Path, str]], zip_filename: str, background_tasks: BackgroundTasks) -> FileResponse:
    return _build_zip_response(entries, zip_filename, background_tasks)


def build_zip_paths(full_paths: List[Path], zip_filename: str, background_tasks: BackgroundTasks) -> FileResponse:
    budget = new_zip_discovery_budget()
    entries: list[ZipEntry] = []
    used_roots = set()
    discovered_identities: set[ZipFileIdentity] = set()
    media_root = get_settings().MEDIA_ROOT
    for root in full_paths:
        budget.charge_requested_root()
        if not root.exists():
            continue
        base = unique_arcname(root.name or 'folder', used_roots)
        entries.extend(collect_boundary_zip_entries(
            root,
            base,
            physical_root=media_root,
            budget=budget,
            charge_root=False,
            discovered_identities=discovered_identities,
        ))

    return _build_zip_response(entries, zip_filename, background_tasks)


def build_zip_file(full_paths: List[Path], zip_filename: str, background_tasks: BackgroundTasks) -> FileResponse:
    return build_zip_paths(full_paths, zip_filename, background_tasks)


def build_zip_dir(root_dir: Path, zip_filename: str, background_tasks: BackgroundTasks) -> FileResponse:
    zip_filename = (zip_filename or root_dir.name or 'folder').strip()
    if not zip_filename.lower().endswith('.zip'):
        zip_filename += '.zip'

    return build_zip_paths([root_dir], zip_filename, background_tasks)
