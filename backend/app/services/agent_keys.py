from __future__ import annotations

import hashlib
import secrets
import time
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AgentApiKey, AgentMutationReceipt

AGENT_KEY_PREFIX = 'vioak'


def _hash_agent_secret(token: str) -> str:
    return hashlib.sha256((token or '').encode()).hexdigest()


def generate_agent_key_token() -> tuple[str, str]:
    key_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(24)
    token = f'{AGENT_KEY_PREFIX}_{key_id}_{secret}'
    return key_id, token


def serialize_agent_key(record: AgentApiKey) -> dict:
    return {
        'id': record.id,
        'name': record.name,
        'user_id': record.user_id,
        'key_prefix': record.key_prefix,
        'is_active': bool(record.is_active),
        'created_by': record.created_by,
        'created_at': record.created_at,
        'updated_at': record.updated_at,
        'last_used_at': record.last_used_at,
        'revoked_at': record.revoked_at,
    }


def create_agent_key(db: Session, *, name: str | None, user_id: str | None, created_by: str | None) -> tuple[AgentApiKey, str]:
    normalized_name = (name or '').strip() or 'Agent key'

    key_id, token = generate_agent_key_token()
    now = time.time()
    record = AgentApiKey(
        id=key_id,
        name=normalized_name,
        user_id=(user_id or '').strip(),
        key_prefix=token[:12],
        secret_hash=_hash_agent_secret(token),
        encrypted_token=None,
        scopes_json='[]',
        is_active=True,
        created_by=created_by,
        created_at=now,
        updated_at=now,
        revoked_at=None,
    )
    if not record.user_id:
        record.user_id = (created_by or '').strip() or 'admin'
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, token


def update_agent_key(db: Session, key_id: str, *, name: str | None = None, user_id: str | None = None, is_active: bool | None = None) -> AgentApiKey:
    record = db.query(AgentApiKey).filter(AgentApiKey.id == key_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail='Agent key not found')

    if name is not None:
        record.name = name.strip() or 'Agent key'
    if user_id is not None:
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            raise HTTPException(status_code=400, detail='Agent key user is required')
        record.user_id = normalized_user_id
    if is_active is not None:
        record.is_active = bool(is_active)
        record.revoked_at = None if record.is_active else time.time()
    record.updated_at = time.time()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def reissue_agent_key(db: Session, key_id: str) -> tuple[AgentApiKey, str]:
    record = db.query(AgentApiKey).filter(AgentApiKey.id == key_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail='Agent key not found')
    _new_key_id, token = generate_agent_key_token()
    now = time.time()
    record.key_prefix = token[:12]
    record.secret_hash = _hash_agent_secret(token)
    record.encrypted_token = None
    record.is_active = True
    record.revoked_at = None
    record.updated_at = now
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, token


def revoke_agent_key(db: Session, key_id: str) -> AgentApiKey:
    record = db.query(AgentApiKey).filter(AgentApiKey.id == key_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail='Agent key not found')
    record.is_active = False
    record.revoked_at = time.time()
    record.updated_at = record.revoked_at
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def delete_agent_key(db: Session, key_id: str) -> None:
    record = db.query(AgentApiKey).filter(AgentApiKey.id == key_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail='Agent key not found')
    db.query(AgentMutationReceipt).filter(AgentMutationReceipt.agent_key_id == key_id).delete()
    db.delete(record)
    db.commit()


def list_agent_keys(db: Session) -> list[AgentApiKey]:
    return db.query(AgentApiKey).order_by(AgentApiKey.created_at.desc()).all()


def resolve_agent_key_record(db: Session, token: str | None) -> AgentApiKey | None:
    normalized = (token or '').strip()
    if not normalized:
        return None
    record = db.query(AgentApiKey).filter(AgentApiKey.secret_hash == _hash_agent_secret(normalized)).first()
    if record is None or not record.is_active:
        return None
    return record


def touch_agent_key(record: AgentApiKey, db: Session) -> AgentApiKey:
    record.last_used_at = time.time()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
