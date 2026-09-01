from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Optional

from fastapi import Cookie, Header, HTTPException

from app.config import get_settings
from app.db import SessionLocal
from app.models import UserSession
from app.services.agent_keys import resolve_agent_key_record, touch_agent_key
from app.services.user_access import (
    canonical_user_role,
    effective_app_access,
    is_admin_user,
    normalize_app_access,
)

settings = get_settings()
SESSION_TTL_SECONDS = settings.SESSION_COOKIE_MAX_AGE
PBKDF2_ITERATIONS = 310000
PBKDF2_PREFIX = 'pbkdf2_sha256'
_request_agent_key: ContextVar[str | None] = ContextVar('vueio_request_agent_key', default=None)


def set_request_agent_key(agent_key: str | None) -> Token:
    """Expose the request's alternate credential to legacy session dependencies."""
    return _request_agent_key.set((agent_key or '').strip() or None)


def reset_request_agent_key(token: Token) -> None:
    _request_agent_key.reset(token)


def get_request_agent_key() -> str | None:
    return _request_agent_key.get()


def _legacy_sha256_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_PREFIX}${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith(f'{PBKDF2_PREFIX}$'):
        try:
            _prefix, iterations_s, salt_b64, derived_b64 = password_hash.split('$', 3)
            iterations = int(iterations_s)
            salt = base64.b64decode(salt_b64.encode())
            expected = base64.b64decode(derived_b64.encode())
            candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
            return hmac.compare_digest(candidate, expected)
        except Exception:
            return False
    candidate = _legacy_sha256_hash(password)
    try:
        return hmac.compare_digest(candidate, password_hash)
    except Exception:
        return candidate == password_hash


def needs_password_rehash(password_hash: str | None) -> bool:
    return not bool(password_hash and password_hash.startswith(f'{PBKDF2_PREFIX}$'))


def _normalize_user_records(users: dict) -> dict:
    normalized: dict = {}
    for username, record in (users or {}).items():
        item = dict(record or {})
        item.pop('permissions', None)
        item['role'] = canonical_user_role(item.get('role'))
        item['app_access'] = normalize_app_access(item.get('app_access'))
        normalized[username] = item
    return normalized


@contextlib.contextmanager
def _locked_users_file(exclusive: bool):
    settings.users_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = settings.users_file.with_suffix(settings.users_file.suffix + '.lock')
    with open(lock_path, 'a+') as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _fsync_parent(path: Path) -> None:
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def load_users() -> dict:
    """Load users from JSON file."""
    with _locked_users_file(exclusive=False):
        return _read_users_unlocked()


def save_users(users: dict) -> None:
    """Save users to JSON file."""
    with _locked_users_file(exclusive=True):
        _write_users_unlocked(users)


def _read_users_unlocked() -> dict:
    if not settings.users_file.exists():
        return {}
    with open(settings.users_file, 'r') as handle:
        users = json.load(handle)
    return _normalize_user_records(users)


def _write_users_unlocked(users: dict) -> None:
    normalized = _normalize_user_records(users)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f'.{settings.users_file.name}.',
        suffix='.tmp',
        dir=settings.users_file.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(normalized, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, settings.users_file)
        _fsync_parent(settings.users_file)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise


def mutate_users(mutator: Callable[[dict], object]) -> object:
    """Hold the users.json write lock across read, mutation, normalize, and replace."""
    with _locked_users_file(exclusive=True):
        users = _read_users_unlocked()
        result = mutator(users)
        _write_users_unlocked(users)
        return result


def mutate_users_and_revoke_sessions(
    mutator: Callable[[dict], object],
    user_id: str,
    *,
    exclude_session_id: str | None = None,
) -> object:
    """Mutate users and revoke sessions without allowing a login between them."""
    with _locked_users_file(exclusive=True):
        users = _read_users_unlocked()
        result = mutator(users)
        destroy_user_sessions(user_id, exclude_session_id=exclude_session_id)
        _write_users_unlocked(users)
        return result


def serialize_auth_user(user: dict) -> dict:
    return {
        'id': user['id'],
        'username': user['username'],
        'display_name': user.get('display_name') or user['username'],
        'role': canonical_user_role(user.get('role')),
        'app_access': effective_app_access(user),
    }


def upgrade_user_password_hash(username: str, password: str) -> None:
    def mutator(users: dict) -> None:
        user = users.get(username)
        if not user:
            return
        if not needs_password_rehash(user.get('password_hash')):
            return
        user['password_hash'] = hash_password(password)

    mutate_users(mutator)


def create_session(user_id: str) -> str:
    session_id = str(uuid.uuid4())
    now = time.time()
    db = SessionLocal()
    try:
        db.add(UserSession(id=session_id, user_id=user_id, created_at=now, last_accessed=now, expires_at=now + SESSION_TTL_SECONDS))
        db.commit()
        return session_id
    finally:
        db.close()


def authenticate_and_create_session(username: str, password: str) -> tuple[dict, str]:
    """Verify credentials and create the session under one users-file read lock."""
    with _locked_users_file(exclusive=False):
        users = _read_users_unlocked()
        if not users:
            raise HTTPException(status_code=409, detail='Initial setup required')

        user = users.get(username)
        if not user or not verify_password(password, user.get('password_hash') or ''):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        session_id = create_session(user['id'])
        should_rehash = needs_password_rehash(user.get('password_hash'))

    if should_rehash:
        upgrade_user_password_hash(user['username'], password)
    return user, session_id


def destroy_session(session_id: Optional[str]) -> None:
    if not session_id:
        return
    db = SessionLocal()
    try:
        db.query(UserSession).filter(UserSession.id == session_id).delete()
        db.commit()
    finally:
        db.close()


def destroy_user_sessions(user_id: str, *, exclude_session_id: str | None = None) -> None:
    db = SessionLocal()
    try:
        query = db.query(UserSession).filter(UserSession.user_id == user_id)
        if exclude_session_id:
            query = query.filter(UserSession.id != exclude_session_id)
        query.delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def get_user_from_session(session_id: str | None, *, allow_agent_fallback: bool = True) -> Optional[dict]:
    if not session_id:
        return get_user_from_agent_key(get_request_agent_key()) if allow_agent_fallback else None

    now = time.time()
    db = SessionLocal()
    try:
        session = db.query(UserSession).filter(UserSession.id == session_id).first()
        if not session:
            return get_user_from_agent_key(get_request_agent_key()) if allow_agent_fallback else None
        if session.expires_at <= now:
            db.delete(session)
            db.commit()
            return get_user_from_agent_key(get_request_agent_key()) if allow_agent_fallback else None
        session.last_accessed = now
        session.expires_at = now + SESSION_TTL_SECONDS
        db.commit()
        user_id = session.user_id
    finally:
        db.close()

    users = load_users()
    user = users.get(user_id)
    if user:
        return user
    return get_user_from_agent_key(get_request_agent_key()) if allow_agent_fallback else None


def get_user_from_agent_key(agent_key: str | None) -> Optional[dict]:
    if not agent_key:
        return None
    db = SessionLocal()
    try:
        record = resolve_agent_key_record(db, agent_key)
        if record is None:
            return None
        touch_agent_key(record, db)
        user_id = record.user_id
    finally:
        db.close()

    users = load_users()
    user = users.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail='Agent key owner is no longer active')
    return user


def get_request_user(
    vueio_session: str | None = Cookie(None),
    agent_key: str | None = Header(None, alias='X-Vueio-Agent-Key'),
) -> tuple[dict, str]:
    user = get_user_from_session(vueio_session, allow_agent_fallback=False)
    if user:
        return user, 'session'
    user = get_user_from_agent_key(agent_key)
    if user:
        return user, 'agent_key'
    raise HTTPException(status_code=401, detail='Authentication required')


def require_auth(vueio_session: str | None = Cookie(None)) -> dict:
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Not authenticated')
    return user


def require_admin(vueio_session: str | None = Cookie(None)) -> dict:
    user = require_auth(vueio_session)
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail='Admin access required')
    return user
