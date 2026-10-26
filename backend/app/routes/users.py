from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Body, Cookie, HTTPException
from pydantic import BaseModel, Field

from app.services.auth import (
    hash_password,
    load_users,
    mutate_users,
    mutate_users_and_revoke_sessions,
    require_auth,
    require_signed_in_user,
)
from app.services.user_access import (
    NEW_MEMBER_APP_ACCESS,
    app_access_is_subset,
    canonical_user_role,
    effective_app_access,
    has_app_access,
    is_admin_user,
    normalize_app_access,
)
from app.services.user_validation import (
    normalize_display_name,
    normalize_username,
    validate_password,
)

router = APIRouter(tags=['users'])


class AppAccess(BaseModel):
    file_browser: bool = False
    project_manager: bool = Field(False, description='Open the projects that the member is added to. When false, manage_project_content, create_projects and delete_projects are also false.')
    manage_project_content: bool = Field(False, description='Create and organize trackers, shots, assignments and project settings.')
    create_projects: bool = Field(False, description='Create projects. Also turns on manage_project_content.')
    delete_projects: bool = Field(False, description='Delete projects that the member can manage. Also turns on manage_project_content.')
    manage_members: bool = False


class UserCreate(BaseModel):
    username: str = Field(max_length=48, description='3 to 48 letters, digits, dots, dashes or underscores. It is also the user id.')
    password: str = Field(max_length=1024, description='At least 8 characters.')
    display_name: str = Field(max_length=120)
    role: str = Field('member', description="'admin' or 'member'.")
    app_access: Optional[AppAccess] = Field(None, description='Access flags for a member. Without it, the member can open projects only. Admins get all access.')


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    password: Optional[str] = Field(default=None, max_length=1024, description='At least 8 characters. Signs the user out everywhere.')
    role: Optional[str] = Field(None, description="'admin' or 'member'.")
    app_access: Optional[AppAccess] = Field(None, description='Replaces all access flags. Flags that you leave out become false.')


def _require_member_manager(vueio_session: str | None) -> dict:
    user = require_auth(vueio_session)
    if not has_app_access(user, 'manage_members'):
        raise HTTPException(status_code=403, detail='Member management access required')
    return user


def _require_remaining_admin(users: dict) -> None:
    if not any(is_admin_user(user) for user in users.values()):
        raise HTTPException(status_code=400, detail='At least one administrator is required')


def _validated_role(value: object) -> str:
    role = str(value or '').strip().lower()
    if role not in {'admin', 'member', 'artist'}:
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'member'.")
    return canonical_user_role(role)


def _actor_can_manage_user(actor: dict, target: dict) -> bool:
    if is_admin_user(actor):
        return True
    if is_admin_user(target):
        return False
    return app_access_is_subset(effective_app_access(target), effective_app_access(actor))


def _require_actor_can_manage_user(actor: dict, target: dict) -> None:
    if not _actor_can_manage_user(actor, target):
        raise HTTPException(status_code=403, detail='You cannot manage an account with higher access than your own')


def _serialize_user(entry: dict, actor: dict) -> dict:
    return {
        'id': entry['id'],
        'username': entry['username'],
        'display_name': entry['display_name'],
        'role': canonical_user_role(entry.get('role')),
        'app_access': effective_app_access(entry),
        'created_at': entry.get('created_at'),
        'can_manage': _actor_can_manage_user(actor, entry),
    }


@router.get('/api/users', summary='List user accounts')
def list_users(vueio_session: str | None = Cookie(None)):
    """List every user account with its role and app access.

    `can_manage` tells whether you can change or delete that account.
    """
    actor = _require_member_manager(vueio_session)
    users = load_users()
    return [_serialize_user(entry, actor) for entry in users.values()]


@router.post('/api/users', summary='Create a user account')
def create_user(data: UserCreate = Body(...), vueio_session: str | None = Cookie(None)):
    """Create a user account with a password.

    Agent keys cannot do this, because the account has a password. The person
    must create it in Vue.io. The username becomes the user id.
    """
    # A new account has a password, which is a credential: people only.
    require_signed_in_user(vueio_session)
    actor = _require_member_manager(vueio_session)

    role = _validated_role(data.role)
    if role == 'admin' and not is_admin_user(actor):
        raise HTTPException(status_code=403, detail='Only an administrator can create another administrator')
    username = normalize_username(data.username)
    password = validate_password(data.password)
    display_name = normalize_display_name(data.display_name, fallback=username)
    app_access = (
        normalize_app_access(data.app_access.model_dump())
        if data.app_access is not None
        else NEW_MEMBER_APP_ACCESS.copy()
    )
    if role == 'admin':
        app_access = normalize_app_access(None)
    elif not is_admin_user(actor) and not app_access_is_subset(app_access, effective_app_access(actor)):
        raise HTTPException(status_code=403, detail='You cannot grant access that you do not have')

    def mutator(users: dict) -> None:
        if username in users:
            raise HTTPException(status_code=400, detail='Username already exists')
        users[username] = {
            'id': username,
            'username': username,
            'password_hash': hash_password(password),
            'display_name': display_name,
            'role': role,
            'app_access': app_access,
            'created_at': time.time(),
        }

    mutate_users(mutator)
    return {'status': 'created', 'id': username}


@router.put('/api/users/{user_id}', summary='Update a user account')
def update_user(user_id: str, data: UserUpdate = Body(...), vueio_session: str | None = Cookie(None)):
    """Change the display name, role, app access or password of a user account.

    Fields that you leave out keep their value. Agent keys can change the
    display name, role and app access, but cannot set a password. At least one
    admin account must remain.
    """
    actor = _require_member_manager(vueio_session)
    if data.password:
        require_signed_in_user(vueio_session)
    next_password = validate_password(data.password) if data.password else None

    def mutator(users: dict) -> None:
        if user_id not in users:
            raise HTTPException(status_code=404, detail='User not found')

        user = users[user_id]
        _require_actor_can_manage_user(actor, user)
        if data.display_name is not None:
            user['display_name'] = normalize_display_name(data.display_name, fallback=user['username'])
        if next_password is not None:
            user['password_hash'] = hash_password(next_password)
        if data.role is not None:
            next_role = _validated_role(data.role)
            if next_role == 'admin' and not is_admin_user(actor):
                raise HTTPException(status_code=403, detail='Only an administrator can create another administrator')
            if is_admin_user(user) and not is_admin_user(actor):
                raise HTTPException(status_code=403, detail='Administrator accounts are protected')
            if next_role == 'member' and is_admin_user(user) and data.app_access is None:
                user['app_access'] = NEW_MEMBER_APP_ACCESS.copy()
            user['role'] = next_role
        if data.app_access is not None:
            user['app_access'] = normalize_app_access(data.app_access.model_dump())
        if not is_admin_user(user) and not is_admin_user(actor):
            if not app_access_is_subset(effective_app_access(user), effective_app_access(actor)):
                raise HTTPException(status_code=403, detail='You cannot grant access that you do not have')
        _require_remaining_admin(users)

    if next_password is not None:
        mutate_users_and_revoke_sessions(mutator, user_id)
    else:
        mutate_users(mutator)
    return {'status': 'updated'}


@router.delete('/api/users/{user_id}', summary='Delete a user account')
def delete_user(user_id: str, vueio_session: str | None = Cookie(None)):
    """Delete a user account. This is permanent.

    The user is signed out everywhere, and the agent keys of the user are
    deleted. You cannot delete your own account or the last admin account.
    """
    current_user = _require_member_manager(vueio_session)
    if user_id == current_user['id']:
        raise HTTPException(status_code=400, detail='Cannot delete your own account')

    def mutator(users: dict) -> None:
        if user_id not in users:
            raise HTTPException(status_code=404, detail='User not found')
        _require_actor_can_manage_user(current_user, users[user_id])
        if is_admin_user(users[user_id]) and not is_admin_user(current_user):
            raise HTTPException(status_code=403, detail='Administrator accounts are protected')
        del users[user_id]
        _require_remaining_admin(users)

    mutate_users_and_revoke_sessions(mutator, user_id)
    return {'status': 'deleted'}
