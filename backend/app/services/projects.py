from __future__ import annotations

import json
import hashlib
import os
import re
import stat
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings
from app.services.project_permissions import make_project_path_smb_mutable

settings = get_settings()

def validate_safe_id(value: str, name: str = 'ID') -> str:
    if not value or not value.strip():
        raise HTTPException(status_code=400, detail=f'{name} is required')
    value = value.strip()
    if '..' in value or '/' in value or '\\' in value:
        raise HTTPException(status_code=400, detail=f'Invalid {name}')
    return value


def get_project_dir(project_id: str) -> Path:
    validate_safe_id(project_id, 'project_id')
    return settings.projects_dir / project_id


def normalize_project_storage_path(value: str | None, *, allow_empty: bool = False) -> str:
    normalized = str(value or '').strip().replace('\\', '/').strip('/')
    if not normalized:
        if allow_empty:
            return ''
        raise HTTPException(status_code=400, detail='Project storage path is required')
    parts = [part for part in normalized.split('/') if part]
    if any(part in {'.', '..'} for part in parts):
        raise HTTPException(status_code=400, detail='Invalid project storage path')
    return '/'.join(parts)


def _configured_custom_storage_roots() -> dict[str, dict]:
    raw = str(settings.PROJECT_STORAGE_ROOTS or '').strip()
    if not raw:
        return {}
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError('PROJECT_STORAGE_ROOTS must be a JSON object mapping names to paths') from exc
    if not isinstance(values, dict):
        raise RuntimeError('PROJECT_STORAGE_ROOTS must be a JSON object mapping names to paths')

    roots = {}
    sentinels: set[str] = set()
    for label, value in values.items():
        if not isinstance(value, dict):
            raise RuntimeError(
                'PROJECT_STORAGE_ROOTS entries must include both path and sentinel; '
                'adopt the storage root before starting Vueio'
            )
        path = value.get('path')
        sentinel = str(value.get('sentinel') or '').strip()
        root_id = re.sub(r'[^a-z0-9_-]+', '-', str(label).strip().lower()).strip('-')
        if not root_id or root_id == 'data' or not str(path or '').strip():
            raise RuntimeError('PROJECT_STORAGE_ROOTS contains an invalid name or path')
        if not re.fullmatch(r'[a-f0-9]{32,128}', sentinel):
            raise RuntimeError('PROJECT_STORAGE_ROOTS contains a missing or invalid storage sentinel')
        configured_path = Path(str(path).strip())
        if not configured_path.is_absolute():
            raise RuntimeError('PROJECT_STORAGE_ROOTS paths must be absolute')
        resolved_path = configured_path.resolve(strict=False)
        if root_id in roots:
            raise RuntimeError('PROJECT_STORAGE_ROOTS contains duplicate normalized names')
        if sentinel in sentinels:
            raise RuntimeError('PROJECT_STORAGE_ROOTS contains duplicate storage sentinels')
        for existing in roots.values():
            existing_path = existing['path']
            if (
                resolved_path == existing_path
                or resolved_path.is_relative_to(existing_path)
                or existing_path.is_relative_to(resolved_path)
            ):
                raise RuntimeError('PROJECT_STORAGE_ROOTS paths must not overlap')
        roots[root_id] = {
            'label': str(label).strip(),
            'path': resolved_path,
            'sentinel': sentinel,
        }
        sentinels.add(sentinel)
    return roots


def storage_root_is_available(item: dict) -> bool:
    path = item['path']
    if not path.is_dir():
        return False
    sentinel = item.get('sentinel')
    if not sentinel or not re.fullmatch(r'[a-f0-9]{32,128}', sentinel):
        return False
    marker = path / '.vueio-storage-id'
    descriptor = None
    try:
        descriptor = os.open(
            marker,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return False
        payload = os.read(descriptor, 130)
        if os.read(descriptor, 1):
            return False
        # Command-line registration records the token with an ordinary
        # trailing newline. Do not silently accept spaces or other control
        # characters that the installer would reject.
        value = payload.decode('ascii').rstrip('\n')
        return bool(re.fullmatch(r'[a-f0-9]{32,128}', value)) and value == sentinel
    except (OSError, UnicodeDecodeError):
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def configured_project_storage_catalog() -> dict[str, dict]:
    # External storage is configured only through the explicit catalog. The
    # expected identity must come from configuration rather than from whatever
    # filesystem happens to be mounted at startup.
    return _configured_custom_storage_roots()


def configured_project_storage_roots() -> dict[str, Path]:
    roots = {'data': settings.projects_dir}
    roots.update({root_id: item['path'] for root_id, item in configured_project_storage_catalog().items()})
    return roots


def resolve_storage_location(storage_root: str, storage_path: str) -> Path:
    root_name = str(storage_root or 'data').strip().lower()
    catalog = configured_project_storage_catalog()
    external_item = catalog.get(root_name)
    if root_name != 'data' and external_item is not None and not storage_root_is_available(external_item):
        raise HTTPException(
            status_code=409,
            detail='Selected storage location is unavailable or its mounted filesystem changed',
        )
    base = configured_project_storage_roots().get(root_name)
    if base is None:
        raise HTTPException(status_code=409, detail='Selected storage location is not configured')
    relative = normalize_project_storage_path(storage_path)
    base = base.resolve()
    target = (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Project storage path escapes its configured root') from exc
    return target


def resolve_project_root(project) -> Path:
    storage_root = str(getattr(project, 'storage_root', None) or 'data').strip().lower()
    storage_path = str(getattr(project, 'storage_path', None) or getattr(project, 'id', '')).strip()
    return resolve_storage_location(storage_root, storage_path)


def resolve_horizon_project_root(db, project_id: str) -> Path:
    from app.models import HorizonProject

    project = db.query(HorizonProject).filter(HorizonProject.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail='Horizons project not found')
    return resolve_project_root(project)


def storage_location_is_read_only(path: Path) -> bool:
    """Return the effective write capability of a storage location.

    For a not-yet-created project folder, inspect its nearest existing parent.
    Read-only mounts and process-level write permissions are both respected.
    """
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        mount_is_read_only = bool(os.statvfs(probe).f_flag & getattr(os, 'ST_RDONLY', 1))
        return mount_is_read_only or not os.access(probe, os.W_OK)
    except OSError:
        return True


def project_storage_is_read_only(project) -> bool:
    try:
        return storage_location_is_read_only(resolve_project_root(project))
    except HTTPException:
        return True


def resolve_project_root_by_id(project_id: str) -> Path:
    """Resolve a Horizons project root without requiring a caller-owned session.

    Legacy JSON projects are intentionally left on the internal data root.
    """
    from app.db import SessionLocal
    from app.models import HorizonProject

    db = SessionLocal()
    try:
        project = db.query(HorizonProject).filter(HorizonProject.id == project_id).first()
        return resolve_project_root(project) if project is not None else get_project_dir(project_id)
    finally:
        db.close()


def require_project_dir(project_id: str) -> Path:
    project_dir = get_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail='Project not found')
    return project_dir


def load_project(project_id: str) -> dict:
    project_dir = get_project_dir(project_id)
    project_file = project_dir / 'project.json'

    old_file = settings.projects_dir / f'{project_id}.json'
    if old_file.exists() and not project_dir.exists():
        project_dir.mkdir(parents=True, exist_ok=True)
        make_project_path_smb_mutable(project_dir)
        with open(old_file, 'r') as handle:
            old_data = json.load(handle)

        shots = old_data.pop('shots', [])
        if shots:
            tracker_data = {'name': 'Main', 'shots': shots, 'created_at': old_data.get('created_at', time.time())}
            tracker_file = project_dir / 'Main.tracker.json'
            with open(tracker_file, 'w') as handle:
                json.dump(tracker_data, handle, indent=2)
            make_project_path_smb_mutable(tracker_file)

        with open(project_file, 'w') as handle:
            json.dump(old_data, handle, indent=2)
        make_project_path_smb_mutable(project_file)
        old_file.unlink()

    if not project_file.exists():
        raise HTTPException(status_code=404, detail='Project not found')
    with open(project_file, 'r') as handle:
        return json.load(handle)


def save_project(project_id: str, data: dict) -> None:
    project_dir = get_project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(project_dir)
    project_file = project_dir / 'project.json'
    with open(project_file, 'w') as handle:
        json.dump(data, handle, indent=2)
    make_project_path_smb_mutable(project_file)


def load_project_links(project_id: str) -> dict:
    project_file = project_links_path(project_id)
    if not project_file.exists():
        return {'links': []}
    with open(project_file, 'r') as handle:
        return json.load(handle)


def project_links_path(project_id: str) -> Path:
    return get_project_dir(project_id) / '.links.json'


def _fsync_directory(path: Path) -> None:
    try:
        directory_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _project_links_bytes(data: dict) -> bytes:
    return f'{json.dumps(data, indent=2)}\n'.encode('utf-8')


def _staged_project_links_path(project_id: str, staged_name: str) -> Path:
    if (
        not staged_name
        or Path(staged_name).name != staged_name
        or not staged_name.startswith('.links.json.')
        or not staged_name.endswith('.pending')
    ):
        raise RuntimeError('Invalid staged project-links filename')
    return get_project_dir(project_id) / staged_name


def stage_project_links(project_id: str, data: dict, *, operation_id: str | None = None) -> tuple[str, str]:
    project_dir = get_project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(project_dir)
    token = operation_id or uuid.uuid4().hex
    validate_safe_id(token, 'operation_id')
    staged_name = f'.links.json.{token}.pending'
    staged_path = _staged_project_links_path(project_id, staged_name)
    payload = _project_links_bytes(data)
    try:
        with open(staged_path, 'xb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        make_project_path_smb_mutable(staged_path)
        with open(staged_path, 'rb') as handle:
            os.fsync(handle.fileno())
        _fsync_directory(project_dir)
    except Exception:
        staged_path.unlink(missing_ok=True)
        raise
    return staged_name, hashlib.sha256(payload).hexdigest()


def project_links_digest(project_id: str) -> str | None:
    project_file = project_links_path(project_id)
    if not project_file.is_file():
        return None
    digest = hashlib.sha256()
    with open(project_file, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def promote_staged_project_links(project_id: str, staged_name: str, expected_digest: str) -> None:
    staged_path = _staged_project_links_path(project_id, staged_name)
    if not staged_path.is_file():
        if project_links_digest(project_id) == expected_digest:
            return
        raise RuntimeError('Staged project links are missing')
    digest = hashlib.sha256(staged_path.read_bytes()).hexdigest()
    if digest != expected_digest:
        raise RuntimeError('Staged project links failed integrity verification')
    project_file = project_links_path(project_id)
    os.replace(staged_path, project_file)
    make_project_path_smb_mutable(project_file)
    with open(project_file, 'rb') as handle:
        os.fsync(handle.fileno())
    _fsync_directory(project_file.parent)


def discard_staged_project_links(project_id: str, staged_name: str) -> None:
    staged_path = _staged_project_links_path(project_id, staged_name)
    if staged_path.exists():
        staged_path.unlink()
        _fsync_directory(staged_path.parent)


def save_project_links(project_id: str, data: dict) -> None:
    staged_name, digest = stage_project_links(project_id, data)
    try:
        promote_staged_project_links(project_id, staged_name, digest)
    finally:
        discard_staged_project_links(project_id, staged_name)
