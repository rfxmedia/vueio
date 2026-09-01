from __future__ import annotations

from collections.abc import Mapping


MEMBER_ROLE = 'member'
ADMIN_ROLE = 'admin'

APP_ACCESS_DEFAULTS = {
    'project_manager': False,
    'file_browser': False,
    'manage_project_content': False,
    'create_projects': False,
    'delete_projects': False,
    'manage_members': False,
}

NEW_MEMBER_APP_ACCESS = {
    **APP_ACCESS_DEFAULTS,
    'project_manager': True,
}

ADMIN_APP_ACCESS = {key: True for key in APP_ACCESS_DEFAULTS}

PROJECT_MANAGEMENT_ACCESS = {
    'manage_project_content',
    'create_projects',
    'delete_projects',
}


def canonical_user_role(value: object) -> str:
    """Vueio has two account types; every historical non-admin role is a Member."""
    return ADMIN_ROLE if str(value or '').strip().lower() == ADMIN_ROLE else MEMBER_ROLE


def is_admin_user(user: Mapping | None) -> bool:
    return bool(user and canonical_user_role(user.get('role')) == ADMIN_ROLE)


def is_member_user(user: Mapping | None) -> bool:
    return bool(user and not is_admin_user(user))


def normalize_app_access(value: object) -> dict[str, bool]:
    source = value if isinstance(value, Mapping) else {}
    result = {
        key: source.get(key) is True
        for key in APP_ACCESS_DEFAULTS
    }
    if not result['project_manager']:
        for key in PROJECT_MANAGEMENT_ACCESS:
            result[key] = False
    elif result['create_projects'] or result['delete_projects']:
        result['manage_project_content'] = True
    return result


def effective_app_access(user: Mapping | None) -> dict[str, bool]:
    if is_admin_user(user):
        return ADMIN_APP_ACCESS.copy()
    return normalize_app_access((user or {}).get('app_access'))


def has_app_access(user: Mapping | None, capability: str) -> bool:
    if capability not in APP_ACCESS_DEFAULTS:
        return False
    return effective_app_access(user)[capability]


def is_restricted_project_member(user: Mapping | None) -> bool:
    return is_member_user(user) and not has_app_access(user, 'manage_project_content')


def app_access_is_subset(candidate: object, ceiling: object) -> bool:
    requested = normalize_app_access(candidate)
    allowed = normalize_app_access(ceiling)
    return all(not enabled or allowed[key] for key, enabled in requested.items())
