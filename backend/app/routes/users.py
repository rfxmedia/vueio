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
    require_admin,
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


class UserCreate(BaseModel):
    username: str = Field(max_length=48)
    password: str = Field(max_length=1024)
    display_name: str = Field(max_length=120)
    role: str = 'artist'
    app_access: Optional[AppAccess] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    password: Optional[str] = Field(default=None, max_length=1024)
    role: Optional[str] = None
    app_access: Optional[AppAccess] = None


def require_admin_cookie(vueio_session: str | None) -> dict:
    return require_admin(vueio_session)


def _require_remaining_admin(users: dict) -> None:
    if not any(user.get('role') == 'admin' for user in users.values()):
        raise HTTPException(status_code=400, detail='At least one administrator is required')


@router.get('/api/users')
def list_users(vueio_session: str | None = Cookie(None)):
    require_admin_cookie(vueio_session)
    users = load_users()
    return [
        {
            'id': entry['id'],
            'username': entry['username'],
            'display_name': entry['display_name'],
            'role': entry['role'],
            'app_access': entry.get('app_access', {'file_browser': False, 'project_manager': False}),
            'created_at': entry.get('created_at'),
        }
        for entry in users.values()
    ]


@router.post('/api/users')
def create_user(data: UserCreate = Body(...), vueio_session: str | None = Cookie(None)):
    require_admin_cookie(vueio_session)

    if data.role not in ('admin', 'artist'):
        raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'artist'.")
    username = normalize_username(data.username)
    password = validate_password(data.password)
    display_name = normalize_display_name(data.display_name, fallback=username)

    def mutator(users: dict) -> None:
        if username in users:
            raise HTTPException(status_code=400, detail='Username already exists')
        users[username] = {
            'id': username,
            'username': username,
            'password_hash': hash_password(password),
            'display_name': display_name,
            'role': data.role,
            'app_access': data.app_access.model_dump() if data.app_access else {'file_browser': False, 'project_manager': False},
            'created_at': time.time(),
        }

    mutate_users(mutator)
    return {'status': 'created', 'id': username}


@router.put('/api/users/{user_id}')
def update_user(user_id: str, data: UserUpdate = Body(...), vueio_session: str | None = Cookie(None)):
    require_admin_cookie(vueio_session)
    next_password = validate_password(data.password) if data.password else None

    def mutator(users: dict) -> None:
        if user_id not in users:
            raise HTTPException(status_code=404, detail='User not found')

        user = users[user_id]
        if data.display_name is not None:
            user['display_name'] = normalize_display_name(data.display_name, fallback=user['username'])
        if next_password is not None:
            user['password_hash'] = hash_password(next_password)
        if data.role is not None:
            if data.role not in ('admin', 'artist'):
                raise HTTPException(status_code=400, detail="Invalid role. Must be 'admin' or 'artist'.")
            user['role'] = data.role
        if data.app_access is not None:
            user['app_access'] = data.app_access.model_dump()
        _require_remaining_admin(users)

    if next_password is not None:
        mutate_users_and_revoke_sessions(mutator, user_id)
    else:
        mutate_users(mutator)
    return {'status': 'updated'}


@router.delete('/api/users/{user_id}')
def delete_user(user_id: str, vueio_session: str | None = Cookie(None)):
    current_user = require_admin_cookie(vueio_session)
    if user_id == current_user['id']:
        raise HTTPException(status_code=400, detail='Cannot delete your own account')

    def mutator(users: dict) -> None:
        if user_id not in users:
            raise HTTPException(status_code=404, detail='User not found')
        del users[user_id]
        _require_remaining_admin(users)

    mutate_users(mutator)
    destroy_user_sessions(user_id)
    return {'status': 'deleted'}
