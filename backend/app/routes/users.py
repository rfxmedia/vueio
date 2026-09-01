from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Body, Cookie, HTTPException
from pydantic import BaseModel, Field

from app.services.auth import (
    destroy_user_sessions,
    hash_password,
    load_users,
    mutate_users,
    mutate_users_and_revoke_sessions,
    require_auth,
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
    project_manager: bool = False
    manage_project_content: bool = False
    create_projects: bool = False
    delete_projects: bool = False
    manage_members: bool = False


class UserCreate(BaseModel):
    username: str = Field(max_length=48)
    password: str = Field(max_length=1024)
    display_name: str = Field(max_length=120)
    role: str = 'member'
    app_access: Optional[AppAccess] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    password: Optional[str] = Field(default=None, max_length=1024)
    role: Optional[str] = None
    app_access: Optional[AppAccess] = None


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


@router.get('/api/users')
def list_users(vueio_session: str | None = Cookie(None)):
    actor = _require_member_manager(vueio_session)
    users = load_users()
    return [_serialize_user(entry, actor) for entry in users.values()]


@router.post('/api/users')
def create_user(data: UserCreate = Body(...), vueio_session: str | None = Cookie(None)):
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


@router.put('/api/users/{user_id}')
def update_user(user_id: str, data: UserUpdate = Body(...), vueio_session: str | None = Cookie(None)):
    actor = _require_member_manager(vueio_session)
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


@router.delete('/api/users/{user_id}')
def delete_user(user_id: str, vueio_session: str | None = Cookie(None)):
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

    mutate_users(mutator)
    destroy_user_sessions(user_id)
    return {'status': 'deleted'}
