from typing import Optional

from fastapi import HTTPException

from app.services.auth import require_auth
from app.services.user_access import has_app_access, is_admin_user


def _permission_path_parts(value: str) -> tuple[str, ...] | None:
    """Return canonical virtual-path components, or None for an unsafe path."""
    raw = str(value or '')
    if '\x00' in raw:
        return None
    parts = tuple(part for part in raw.replace('\\', '/').strip('/').split('/') if part)
    if any(part in {'.', '..'} for part in parts):
        return None
    return parts


def _is_same_or_descendant(candidate: tuple[str, ...], root: tuple[str, ...]) -> bool:
    return candidate[:len(root)] == root


def _has_file_browser_access(user: dict) -> bool:
    return has_app_access(user, 'file_browser')


def check_folder_read_permission(user: dict, path: str) -> bool:
    if not user:
        return False
    candidate = _permission_path_parts(path)
    if candidate is None:
        return False
    if is_admin_user(user):
        return True
    perms = user.get('folder_permissions', []) or []
    if '*' in perms:
        return True
    return any(
        bool(allowed_parts) and _is_same_or_descendant(candidate, allowed_parts)
        for allowed in perms
        if (allowed_parts := _permission_path_parts(allowed)) is not None
    )


def check_folder_navigation_permission(user: dict, path: str) -> bool:
    if check_folder_read_permission(user, path):
        return True
    if not user:
        return False
    candidate = _permission_path_parts(path)
    if candidate is None:
        return False
    return any(
        bool(allowed_parts) and _is_same_or_descendant(allowed_parts, candidate)
        for allowed in (user.get('folder_permissions', []) or [])
        if allowed != '*'
        if (allowed_parts := _permission_path_parts(allowed)) is not None
    )


def check_folder_permission(user: dict, path: str) -> bool:
    """Compatibility alias for browser navigation checks."""
    return check_folder_navigation_permission(user, path)


def require_user_file_browser_read_access(user: dict, path: str) -> dict:
    if not _has_file_browser_access(user):
        raise HTTPException(status_code=403, detail='File Browser access required')
    if not check_folder_read_permission(user, path):
        raise HTTPException(status_code=403, detail='Access denied to this path')
    return user


def require_file_browser_access(vueio_session: Optional[str], path: str = '') -> dict:
    user = require_auth(vueio_session)
    if not _has_file_browser_access(user):
        raise HTTPException(status_code=403, detail='File Browser access required')
    if path and not check_folder_navigation_permission(user, path):
        raise HTTPException(status_code=403, detail='Access denied to this path')
    return user


def require_file_browser_read_access(vueio_session: Optional[str], path: str) -> dict:
    return require_user_file_browser_read_access(require_auth(vueio_session), path)


def filter_items_by_permission(user: dict, items: list) -> list:
    if not user:
        return []
    if is_admin_user(user):
        return items

    folder_permissions = user.get('folder_permissions', [])
    if not folder_permissions:
        return []

    for perm in folder_permissions:
        if str(perm or '').strip('/') == '*':
            return items

    filtered = []
    for item in items:
        item_path = _permission_path_parts(item['path'])
        if item_path is None:
            continue
        for perm in folder_permissions:
            clean_perm = _permission_path_parts(perm)
            if not clean_perm:
                continue
            if (
                _is_same_or_descendant(item_path, clean_perm)
                or _is_same_or_descendant(clean_perm, item_path)
            ):
                filtered.append(item)
                break
    return filtered
