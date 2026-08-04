from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.services.auth import get_user_from_session, require_admin
from app.services.projects import require_project_dir


def check_project_permission(user: dict, project_id: str) -> bool:
    if not user:
        return False
    if user.get('role') == 'admin':
        return True
    perms = user.get('project_permissions', []) or []
    return '*' in perms or project_id in perms


def require_project_auth(project_id: str, vueio_session: str | None) -> dict:
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    if not check_project_permission(user, project_id):
        raise HTTPException(status_code=403, detail='Access denied to this project')
    return user


def require_project_admin(project_id: str, vueio_session: str | None) -> dict:
    user = require_admin(vueio_session)
    require_project_dir(project_id)
    return user


def resolve_authorized_legacy_project_media_target(project_id: str, path: str, user: dict):
    from app.services.file_access import require_user_file_browser_read_access
    from app.services.media_resolution import resolve_media_target, resolve_project_content_target

    full_path, cache_key, storage_scope = resolve_project_content_target(project_id, path)
    if full_path is not None and full_path.is_file():
        return full_path, cache_key, storage_scope
    require_user_file_browser_read_access(user, path)
    media_path, cache_key, storage_scope = resolve_media_target(path, storage_scope='media_root')
    if media_path is not None and media_path.is_file():
        return media_path, cache_key, storage_scope
    return None, None, storage_scope


def verify_path_in_project(path: Path, project_dir: Path):
    try:
        path.resolve().relative_to(project_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail='Access denied')
