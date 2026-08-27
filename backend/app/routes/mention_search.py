from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth import get_request_user
from app.services.horizons_fresh import require_horizon_project_access
from app.services.mention_search import MENTION_TARGET_TYPES, search_project_mentions

router = APIRouter(tags=['mentions'])


def _parse_target_types(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return MENTION_TARGET_TYPES
    requested = tuple(dict.fromkeys(part.strip() for part in value.split(',') if part.strip()))
    if not requested or any(target_type not in MENTION_TARGET_TYPES for target_type in requested):
        raise HTTPException(status_code=400, detail='Invalid mention target types')
    return requested


@router.get('/api/projects/{project_id}/mention-search')
def mention_search(
    project_id: str,
    q: str = Query(default='', max_length=120),
    types: str | None = Query(default=None, max_length=120),
    context_tracker_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=5, ge=1, le=20),
    vueio_session: str | None = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    _project, access_role = require_horizon_project_access(
        db,
        project_id,
        user,
        auth_mode=auth_mode,
        required_role='viewer',
    )
    return search_project_mentions(
        db,
        project_id,
        query=q.strip(),
        target_types=_parse_target_types(types),
        context_tracker_id=(context_tracker_id or '').strip() or None,
        limit=limit,
        user=user,
        access_role=access_role,
    )
