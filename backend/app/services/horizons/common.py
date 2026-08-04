from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.models import HorizonProject


DELETED_PROJECT_STATUS = 'deleted'


PROJECT_STATUSES = {'active', 'on_hold', 'archived', 'not_started', 'in_progress', 'waiting_review', 'edits_requested', 'done'}


SHOT_STATUSES = {'not_started', 'in_progress', 'waiting_review', 'edits_requested', 'done'}


SHOT_STATUS_ORDER = ['not_started', 'in_progress', 'waiting_review', 'edits_requested', 'done']


SHOT_STATUS_LABELS = {
    'not_started': 'Not Started',
    'in_progress': 'In Progress',
    'waiting_review': 'Review',
    'edits_requested': 'Edits Requested',
    'done': 'Done',
}


VISIBILITIES = {'private', 'internal', 'client'}


GRANT_ROLES = {'viewer', 'editor', 'owner'}


ROLE_RANK = {'viewer': 1, 'editor': 2, 'owner': 3, 'admin': 4}


HORIZON_RESERVED_FILENAMES = {'project.json'}


TRACKER_TOOL_ACCESSES = {'admin', 'team', 'all'}


DEFAULT_DELIVERY_MESSAGE = 'Thanks for reviewing with Vue.'


DEFAULT_TRACKER_SETTINGS = {
    'comparison': {
        'enabled': True,
        'access': 'team',
    },
    'details': {
        'enabled': True,
        'access': 'all',
    },
    'brief_preview': {
        'enabled': True,
    },
    'version_review': {
        'enabled': False,
    },
    'delivery': {
        'enabled': False,
        'message': DEFAULT_DELIVERY_MESSAGE,
        'notes': '',
        'links': [],
        'logo_upload_name': '',
    },
}


def _normalize_horizon_tracker_tags(value) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = str(item or '').strip()
        if not tag or tag in {'Uncategorized', 'Untagged'}:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag[:120])
    return tags


def _normalize_project_status(status: str | None) -> str:
    value = (status or 'active').strip().lower()
    if value not in PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid project status')
    return value


def is_deleted_horizon_project(project: HorizonProject | None) -> bool:
    return bool(project and project.status == DELETED_PROJECT_STATUS)


def _normalize_shot_status(status: str | None) -> str:
    value = (status or 'not_started').strip().lower()
    if value not in SHOT_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid shot status')
    return value


def _normalize_visibility(visibility: str | None) -> str:
    value = (visibility or 'private').strip().lower()
    if value not in VISIBILITIES:
        raise HTTPException(status_code=400, detail='Invalid visibility')
    return value


def _normalize_grant_role(role: str | None) -> str:
    value = (role or 'viewer').strip().lower()
    if value not in GRANT_ROLES:
        raise HTTPException(status_code=400, detail='Invalid grant role')
    return value


def _dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or '').strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _normalize_horizon_runtime_path(raw_path: str | None, *, allow_empty: bool = False) -> str:
    value = (raw_path or '').strip().strip('/')
    if not value:
        if allow_empty:
            return ''
        raise HTTPException(status_code=400, detail='Path is required')

    parts = []
    for part in value.split('/'):
        part = part.strip()
        if not part or part == '.':
            continue
        if part == '..':
            raise HTTPException(status_code=400, detail='Parent traversal is not allowed')
        if part.startswith('.'):
            raise HTTPException(status_code=400, detail='Hidden paths are not allowed')
        parts.append(part)
    normalized = '/'.join(parts)
    if not normalized:
        if allow_empty:
            return ''
        raise HTTPException(status_code=400, detail='Path is required')
    return normalized


def _sanitize_horizon_filename(filename: str | None) -> str:
    safe_name = ''.join(c for c in (filename or '') if c.isalnum() or c in '.-_ ').strip()
    safe_name = Path(safe_name).name.strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail='Valid filename is required')
    if safe_name in HORIZON_RESERVED_FILENAMES or safe_name.endswith('.tracker.json'):
        raise HTTPException(status_code=400, detail='Reserved filename')
    if safe_name.startswith('.'):
        raise HTTPException(status_code=400, detail='Hidden filenames are not allowed')
    return safe_name
