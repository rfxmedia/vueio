from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AgentApiKey
from app.services.agent_keys import (
    create_agent_key,
    delete_agent_key,
    reissue_agent_key,
    serialize_agent_key,
    update_agent_key,
)
from app.services.auth import (
    get_user_from_session,
    hash_password,
    mutate_users_and_revoke_sessions,
    verify_password,
)
from app.services.user_validation import validate_password

router = APIRouter(tags=['account'])


class PersonalAgentKeyCreate(BaseModel):
    name: Optional[str] = None


class PersonalAgentKeyUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(max_length=1024)


def _require_current_user(vueio_session: str | None) -> dict:
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    return user


def _current_user_id(user: dict) -> str:
    user_id = (user.get('id') or user.get('username') or '').strip()
    if not user_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    return user_id


def _serialize_personal_key(record: AgentApiKey) -> dict:
    return serialize_agent_key(record)


@router.put('/api/me/password')
def put_my_password(data: PasswordUpdate, vueio_session: str | None = Cookie(None)):
    user = _require_current_user(vueio_session)
    new_password = validate_password(data.new_password, label='New password')

    def mutator(users: dict) -> None:
        user_record = users.get(user.get('username') or user.get('id'))
        if not user_record:
            raise HTTPException(status_code=404, detail='User not found')
        if not verify_password(data.current_password, user_record.get('password_hash') or ''):
            raise HTTPException(status_code=400, detail='Current password is incorrect')
        user_record['password_hash'] = hash_password(new_password)

    mutate_users_and_revoke_sessions(
        mutator,
        _current_user_id(user),
        exclude_session_id=vueio_session,
    )
    return {'status': 'updated'}


def _get_owned_agent_key(db: Session, key_id: str, user_id: str) -> AgentApiKey:
    record = (
        db.query(AgentApiKey)
        .filter(AgentApiKey.id == key_id)
        .filter(AgentApiKey.user_id == user_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail='Agent key not found')
    return record


@router.get('/api/me/agent-keys')
def get_my_agent_keys(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_current_user(vueio_session)
    user_id = _current_user_id(user)
    keys = (
        db.query(AgentApiKey)
        .filter(AgentApiKey.user_id == user_id)
        .order_by(AgentApiKey.created_at.desc())
        .all()
    )
    return {'keys': [_serialize_personal_key(record) for record in keys]}


@router.post('/api/me/agent-keys')
def post_my_agent_key(data: PersonalAgentKeyCreate, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_current_user(vueio_session)
    user_id = _current_user_id(user)
    record, token = create_agent_key(
        db,
        name=data.name,
        user_id=user_id,
        created_by=user_id,
    )
    return {'key': _serialize_personal_key(record), 'token': token}


@router.put('/api/me/agent-keys/{key_id}')
def put_my_agent_key(key_id: str, data: PersonalAgentKeyUpdate, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_current_user(vueio_session)
    user_id = _current_user_id(user)
    _get_owned_agent_key(db, key_id, user_id)
    record = update_agent_key(db, key_id, name=data.name, is_active=data.is_active)
    return {'key': _serialize_personal_key(record)}


@router.post('/api/me/agent-keys/{key_id}/reissue')
def post_my_agent_key_reissue(key_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_current_user(vueio_session)
    user_id = _current_user_id(user)
    _get_owned_agent_key(db, key_id, user_id)
    record, token = reissue_agent_key(db, key_id)
    return {'key': _serialize_personal_key(record), 'token': token}


@router.delete('/api/me/agent-keys/{key_id}')
def delete_my_agent_key(key_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = _require_current_user(vueio_session)
    user_id = _current_user_id(user)
    _get_owned_agent_key(db, key_id, user_id)
    delete_agent_key(db, key_id)
    return {'status': 'deleted', 'id': key_id}
