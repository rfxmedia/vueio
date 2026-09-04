from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AppIdentity
from app.services.app_identity import normalize_team_name, normalize_website_url, save_app_identity, serialize_app_identity
from app.services.auth import create_session, hash_password, load_users, mutate_users, serialize_auth_user
from app.services.user_validation import normalize_display_name, normalize_username, validate_password

router = APIRouter(tags=['setup'])
settings = get_settings()

class SetupCompleteRequest(BaseModel):
    team_name: str = Field(default='My studio', max_length=120)
    website_url: str | None = Field(default=None, max_length=500)
    username: str = Field(default='admin', max_length=48)
    display_name: str = Field(default='', max_length=120)
    password: str = Field(max_length=1024)
    setup_token: str | None = Field(default=None, max_length=256)


def _setup_status_payload() -> dict:
    setup_required = not bool(load_users())
    return {
        'setup_required': setup_required,
        'setup_token_required': bool(setup_required and (settings.VUEIO_SETUP_TOKEN or not settings.is_development)),
    }


def _require_setup_token(submitted_token: str | None) -> None:
    configured_token = str(settings.VUEIO_SETUP_TOKEN or '').strip()
    if not configured_token and settings.is_development:
        return
    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail='Initial setup is locked because VUEIO_SETUP_TOKEN is not configured',
        )
    if not hmac.compare_digest(configured_token, str(submitted_token or '').strip()):
        raise HTTPException(
            status_code=401,
            detail='That setup code is not correct. Copy the current code from the installer, then try again.',
        )


@router.get('/api/setup/status')
def get_setup_status():
    return _setup_status_payload()


@router.post('/api/setup/complete')
def complete_setup(response: Response, data: SetupCompleteRequest = Body(...), db: Session = Depends(get_db)):
    if load_users():
        raise HTTPException(status_code=409, detail='Initial setup is already complete')
    _require_setup_token(data.setup_token)

    password = validate_password(data.password)
    username = normalize_username(data.username)
    display_name = normalize_display_name(data.display_name, fallback=username)
    team_name = normalize_team_name(data.team_name)
    website_url = normalize_website_url(data.website_url)
    now = time.time()
    user = {
        'id': username,
        'username': username,
        'password_hash': hash_password(password),
        'role': 'admin',
        'display_name': display_name,
        'folder_permissions': ['*'],
        'project_permissions': ['*'],
        'app_access': {'file_browser': True, 'project_manager': True},
        'created_at': now,
    }

    def mutator(users: dict) -> None:
        if users:
            raise HTTPException(status_code=409, detail='Initial setup is already complete')
        users[username] = user

    existing_identity = db.query(AppIdentity).filter(AppIdentity.id == 1).first()
    identity_snapshot = None if existing_identity is None else {
        'team_name': existing_identity.team_name,
        'website_url': existing_identity.website_url,
        'logo_upload_name': existing_identity.logo_upload_name,
        'updated_by': existing_identity.updated_by,
        'updated_at': existing_identity.updated_at,
    }
    mutate_users(mutator)
    try:
        identity = save_app_identity(
            db,
            team_name=team_name,
            website_url=website_url,
            updated_by=username,
        )
        session_id = create_session(user['id'])
    except Exception as exc:
        db.rollback()
        current_identity = db.query(AppIdentity).filter(AppIdentity.id == 1).first()
        if identity_snapshot is None:
            if current_identity is not None:
                db.delete(current_identity)
        elif current_identity is not None:
            for field, value in identity_snapshot.items():
                setattr(current_identity, field, value)
        db.commit()

        def rollback_user(users: dict) -> None:
            current = users.get(username)
            if current and current.get('password_hash') == user['password_hash']:
                users.pop(username, None)

        mutate_users(rollback_user)
        raise HTTPException(
            status_code=500,
            detail='Initial setup failed; no changes were saved',
        ) from exc

    response.set_cookie(
        key='vueio_session',
        value=session_id,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=settings.SESSION_COOKIE_MAX_AGE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )

    return {
        'status': _setup_status_payload(),
        'user': serialize_auth_user(user),
        'identity': serialize_app_identity(identity),
    }
