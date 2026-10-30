from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.limiter import limiter
from app.services.auth import (
    authenticate_and_create_session,
    destroy_session,
    get_user_from_session,
    serialize_auth_user,
)
from app.services.network_paths import user_has_network_paths

router = APIRouter(tags=['auth'])
settings = get_settings()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


@router.post('/api/login')
@limiter.limit('5/minute')
def login(request: Request, response: Response, login_data: LoginRequest = Body(...)):
    """Login and create session (rate limited: 5 attempts per minute)."""
    user, session_id = authenticate_and_create_session(login_data.username, login_data.password)
    response.set_cookie(
        key='vueio_session',
        value=session_id,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=settings.SESSION_COOKIE_MAX_AGE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )

    return serialize_auth_user(user)


@router.post('/api/logout')
def logout(response: Response, vueio_session: str | None = Cookie(None)):
    """Logout and clear session."""
    destroy_session(vueio_session)
    response.delete_cookie('vueio_session', secure=settings.SESSION_COOKIE_SECURE, samesite=settings.SESSION_COOKIE_SAMESITE)
    return {'status': 'logged out'}


@router.get('/api/auth/check')
def check_auth(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    """Check if user is authenticated."""
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Not authenticated')

    # True when this person can copy the full network path of files.
    return {**serialize_auth_user(user), 'network_paths': user_has_network_paths(db, user)}
