from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.media import DELIVERY_POSTER_WIDTH, THUMBNAIL_WIDTH, get_file_hash, queue_thumbnail_generation, thumbnail_placeholder_response
from app.services.projects import get_project_dir

settings = get_settings()
STATE_FILENAME = '.horizons-entity-thumbnails.json'
VALID_ENTITY_TYPES = {'project', 'folder'}


def normalize_horizon_thumbnail_entity(entity_type: str, entity_path: str | None = None) -> tuple[str, str | None]:
    normalized_type = (entity_type or 'project').strip().lower()
    if normalized_type not in VALID_ENTITY_TYPES:
        raise ValueError('Invalid thumbnail entity type')

    if normalized_type == 'project':
        return 'project', None

    raw_path = str(entity_path or '').strip().strip('/')
    if not raw_path:
        raise ValueError('Folder thumbnail path is required')

    normalized_path = str(PurePosixPath(raw_path))
    if normalized_path in {'.', ''}:
        raise ValueError('Folder thumbnail path is required')
    if normalized_path.startswith('../') or normalized_path == '..' or normalized_path.startswith('/'):
        raise ValueError('Invalid folder thumbnail path')
    if any(part in {'..', ''} for part in PurePosixPath(normalized_path).parts):
        raise ValueError('Invalid folder thumbnail path')

    return 'folder', normalized_path


def horizon_entity_thumbnail_state_path(project_id: str) -> Path:
    return get_project_dir(project_id) / STATE_FILENAME


def load_horizon_entity_thumbnail_state(project_id: str) -> dict:
    state_path = horizon_entity_thumbnail_state_path(project_id)
    if not state_path.exists():
        return {'project': None, 'folders': {}}
    try:
        data = json.loads(state_path.read_text(encoding='utf-8'))
    except Exception:
        return {'project': None, 'folders': {}}
    project_record = data.get('project') if isinstance(data, dict) else None
    folders = data.get('folders') if isinstance(data, dict) else {}
    if not isinstance(folders, dict):
        folders = {}
    return {
        'project': project_record if isinstance(project_record, dict) else None,
        'folders': {str(key).strip('/'): value for key, value in folders.items() if str(key).strip('/') and isinstance(value, dict)},
    }


def save_horizon_entity_thumbnail_state(project_id: str, state: dict) -> None:
    state_path = horizon_entity_thumbnail_state_path(project_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='thumb-state-', suffix='.json', dir=str(state_path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
        os.replace(tmp_path, state_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def get_horizon_entity_thumbnail_record(project_id: str, entity_type: str, entity_path: str | None = None) -> dict | None:
    normalized_type, normalized_path = normalize_horizon_thumbnail_entity(entity_type, entity_path)
    state = load_horizon_entity_thumbnail_state(project_id)
    if normalized_type == 'project':
        record = state.get('project')
    else:
        record = state.get('folders', {}).get(normalized_path)
    return record if isinstance(record, dict) else None


def set_horizon_entity_thumbnail_record(project_id: str, entity_type: str, record: dict | None, entity_path: str | None = None) -> None:
    normalized_type, normalized_path = normalize_horizon_thumbnail_entity(entity_type, entity_path)
    state = load_horizon_entity_thumbnail_state(project_id)
    if normalized_type == 'project':
        state['project'] = record if isinstance(record, dict) else None
    else:
        folders = state.setdefault('folders', {})
        if isinstance(record, dict):
            folders[normalized_path] = record
        else:
            folders.pop(normalized_path, None)
    save_horizon_entity_thumbnail_state(project_id, state)


def list_horizon_folder_thumbnail_paths(project_id: str) -> set[str]:
    state = load_horizon_entity_thumbnail_state(project_id)
    folders = state.get('folders') or {}
    return {str(path).strip('/') for path, record in folders.items() if str(path).strip('/') and isinstance(record, dict)}


def build_horizon_entity_upload_name(project_id: str, entity_type: str, entity_path: str | None, original_filename: str | None) -> str:
    normalized_type, normalized_path = normalize_horizon_thumbnail_entity(entity_type, entity_path)
    suffix = Path(original_filename or 'thumbnail.jpg').suffix.lower() or '.jpg'
    if suffix not in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}:
        suffix = '.jpg'
    entity_key = f'{project_id}:{normalized_type}:{normalized_path or "project"}'
    token = get_file_hash(entity_key)
    return f'horizon-entity-thumb-{token}{suffix}'


def get_horizon_entity_upload_path(upload_name: str) -> Path:
    return settings.thumbnail_dir / Path(upload_name).name


def project_thumbnail_snapshot(project_id: str, identity: str, *, source: Path | None = None, cached: Path | None = None, poster: bool = False, queue_missing: bool = True):
    """A project cover belongs to app data, not to a movable media file or cache."""
    target = get_project_dir(project_id) / '.thumbnails' / f'{get_file_hash(identity)}-{int(poster)}.jpg'
    rendered = settings.thumbnail_dir / f'project-cover-{get_file_hash(project_id + ":" + identity)}-{int(poster)}.jpg'
    headers = {'Cache-Control': 'private, no-cache'}
    if target.is_file() and target.stat().st_size:
        return FileResponse(target, media_type='image/jpeg', headers=headers)
    if rendered.is_file() and rendered.stat().st_size:
        cached = rendered
    if cached and cached.is_file() and cached.stat().st_size:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=target.parent, suffix='.part')
        try:
            with os.fdopen(fd, 'wb') as output, cached.open('rb') as input_file:
                shutil.copyfileobj(input_file, output)
            os.replace(temporary, target)
        except FileNotFoundError:
            # Cache cleanup can race this request; the original can still render.
            pass
        finally:
            Path(temporary).unlink(missing_ok=True)
        if target.is_file():
            return FileResponse(target, media_type='image/jpeg', headers=headers)
    if source and source.is_file():
        if queue_missing:
            # Keep GPU helper output inside its existing cache-only boundary.
            # The completed frame is adopted into app data on the next request.
            rendered.parent.mkdir(parents=True, exist_ok=True)
            queue_thumbnail_generation(source, rendered, width=DELIVERY_POSTER_WIDTH if poster else THUMBNAIL_WIDTH)
        return thumbnail_placeholder_response()
    if source is not None:
        raise HTTPException(status_code=404, detail='Thumbnail source not found')
    return None
