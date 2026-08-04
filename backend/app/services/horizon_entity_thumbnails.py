from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path, PurePosixPath

from app.config import get_settings
from app.services.media import get_file_hash
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
