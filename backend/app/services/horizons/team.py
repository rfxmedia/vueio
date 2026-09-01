from __future__ import annotations

import time
import uuid

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session, object_session

from app.models import (
    HorizonProjectGrant,
    HorizonShot,
    HorizonShotAssignee,
)
from app.services.auth import load_users
from app.services.naming import slugify
from app.services.project_access import verify_path_in_project
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.user_access import (
    canonical_user_role,
    is_restricted_project_member,
)

from .common import ROLE_RANK, _dedupe_ordered, _normalize_grant_role, _normalize_horizon_runtime_path

def _subject_candidates_for_user(user: dict | None) -> list[tuple[str, str]]:
    if not user:
        return []
    candidates = []
    for subject_type, subject_id in [
        ('user_id', user.get('id')),
        ('username', user.get('username')),
    ]:
        if subject_id and (subject_type, subject_id) not in candidates:
            candidates.append((subject_type, subject_id))
    return candidates


def _user_directory() -> dict:
    return load_users()


def _canonical_user_id(user: dict | None) -> str | None:
    if not user:
        return None
    value = (user.get('id') or user.get('username') or '').strip()
    return value or None


def _is_assignable_team_user(user: dict | None) -> bool:
    return bool(user and canonical_user_role(user.get('role')) in {'admin', 'member'})


def get_horizon_assignable_user(user_ref: str | None) -> dict | None:
    normalized = str(user_ref or '').strip()
    if not normalized:
        return None
    users = _user_directory()
    direct = users.get(normalized)
    if _is_assignable_team_user(direct):
        return direct
    for user in users.values():
        if not _is_assignable_team_user(user):
            continue
        if normalized in {
            str(user.get('id') or '').strip(),
            str(user.get('username') or '').strip(),
        }:
            return user
    return None


def serialize_horizon_team_user(user: dict | None) -> dict | None:
    if not _is_assignable_team_user(user):
        return None
    return {
        'id': _canonical_user_id(user),
        'username': user.get('username') or user.get('id'),
        'display_name': user.get('display_name') or user.get('username') or user.get('id'),
        'role': canonical_user_role(user.get('role')),
    }


def _resolve_horizon_assignee_ids(user_refs: list[str | None] | None) -> list[str]:
    assignee_ids: list[str] = []
    for user_ref in user_refs or []:
        if not user_ref:
            continue
        assignee = get_horizon_assignable_user(user_ref)
        if assignee is None:
            raise HTTPException(status_code=400, detail='Assignable team account not found')
        assignee_id = _canonical_user_id(assignee)
        if assignee_id:
            assignee_ids.append(assignee_id)
    return _dedupe_ordered(assignee_ids)


def _ensure_horizon_project_memberships_for_assignees(db: Session, *, project_id: str, user_ids: list[str]) -> None:
    from .projects import get_horizon_project

    project = get_horizon_project(db, project_id)
    now = time.time()
    for user_id in user_ids:
        user = get_horizon_assignable_user(user_id)
        if user is None:
            raise HTTPException(status_code=400, detail='Assignable team account not found')
        for subject_type, subject_id in _subject_candidates_for_user(user):
            _upsert_horizon_project_grant(
                db,
                project_id=project_id,
                subject_type=subject_type,
                subject_id=subject_id,
                role='editor',
                now=now,
                allow_downgrade=False,
            )
        ensure_horizon_project_user_workspace(db, project_id, user)
    if user_ids:
        project.updated_at = now
        db.add(project)


def _shot_assignee_rows(db: Session, shot: HorizonShot) -> list[HorizonShotAssignee]:
    return (
        db.query(HorizonShotAssignee)
        .filter(HorizonShotAssignee.shot_id == shot.id)
        .order_by(
            HorizonShotAssignee.sort_order.asc(),
            HorizonShotAssignee.created_at.asc(),
            HorizonShotAssignee.id.asc(),
        )
        .all()
    )


def get_horizon_shot_assignee_ids(shot: HorizonShot, db: Session | None = None) -> list[str]:
    active_db = db or object_session(shot)
    if active_db is not None:
        user_ids = [row.user_id for row in _shot_assignee_rows(active_db, shot) if row.user_id]
        if user_ids:
            return _dedupe_ordered(user_ids)
    return _dedupe_ordered([shot.assignee_user_id] if shot.assignee_user_id else [])


def _horizon_shot_assignment_clause(subject_ids: set[str]):
    """Match current assignee rows, falling back to the legacy primary assignee."""
    normalized_ids = tuple(value for value in subject_ids if value)
    matching_assignee = exists().where(and_(
        HorizonShotAssignee.shot_id == HorizonShot.id,
        HorizonShotAssignee.user_id.in_(normalized_ids),
    ))
    any_assignee = exists().where(HorizonShotAssignee.shot_id == HorizonShot.id)
    return or_(
        matching_assignee,
        and_(~any_assignee, HorizonShot.assignee_user_id.in_(normalized_ids)),
    )


def serialize_horizon_shot_assignees(shot: HorizonShot, db: Session | None = None) -> list[dict]:
    assignees: list[dict] = []
    for user_id in get_horizon_shot_assignee_ids(shot, db):
        summary = serialize_horizon_team_user(get_horizon_assignable_user(user_id))
        if summary:
            assignees.append(summary)
    return assignees


def get_horizon_user_workspace_path(user: dict | None) -> str:
    team_user = serialize_horizon_team_user(user)
    if not team_user:
        raise HTTPException(status_code=400, detail='Assignable team account required')
    slug_source = team_user.get('username') or team_user.get('id') or 'workspace'
    return slugify(str(slug_source), 'workspace')


def is_horizon_user_workspace_path(user: dict | None, path: str | None) -> bool:
    workspace_path = get_horizon_user_workspace_path(user)
    normalized_path = str(path or '').strip().strip('/')
    return normalized_path == workspace_path or normalized_path.startswith(f'{workspace_path}/')


def is_horizon_workspace_root_path(path: str | None) -> bool:
    normalized_path = str(path or '').strip().strip('/')
    if not normalized_path or '/' in normalized_path:
        return False
    for user in _user_directory().values():
        if not _is_assignable_team_user(user):
            continue
        if normalized_path == get_horizon_user_workspace_path(user):
            return True
    return False


def is_restricted_horizon_artist(user: dict | None, access_role: str | None = None) -> bool:
    # Project roles describe write capability. Restricted Member visibility is
    # assignment-scoped until an administrator grants project-content control.
    return is_restricted_project_member(user)


def ensure_horizon_project_user_workspace(db: Session, project_id: str, user: dict | None) -> str:
    from app.services.projects import project_storage_is_read_only, resolve_project_root
    from .projects import ensure_horizon_project_runtime_dir, get_horizon_project

    workspace_path = get_horizon_user_workspace_path(user)
    project = get_horizon_project(db, project_id)
    if project_storage_is_read_only(project):
        return workspace_path
    project_dir = ensure_horizon_project_runtime_dir(db, project_id)
    workspace_dir = project_dir / workspace_path
    verify_path_in_project(workspace_dir, project_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(workspace_dir)
    return workspace_path


def require_horizon_user_workspace_path(
    db: Session,
    project_id: str,
    user: dict | None,
    path: str | None,
    *,
    allow_workspace_root: bool = True,
    outside_detail: str = 'Members with review access can only modify items inside their workspace',
    root_detail: str = 'Cannot modify the workspace root',
) -> str:
    """Return a canonical project path confined to a restricted Member workspace."""
    normalized_path = _normalize_horizon_runtime_path(path, allow_empty=True)
    workspace_path = ensure_horizon_project_user_workspace(db, project_id, user)
    if not normalized_path:
        if allow_workspace_root:
            return workspace_path
        raise HTTPException(status_code=403, detail=outside_detail)
    if normalized_path != workspace_path and not normalized_path.startswith(f'{workspace_path}/'):
        raise HTTPException(status_code=403, detail=outside_detail)
    if normalized_path == workspace_path and not allow_workspace_root:
        raise HTTPException(status_code=403, detail=root_detail)
    return normalized_path


def _upsert_horizon_project_grant(
    db: Session,
    *,
    project_id: str,
    subject_type: str,
    subject_id: str,
    role: str,
    now: float | None = None,
    allow_downgrade: bool = True,
) -> HorizonProjectGrant:
    normalized_role = _normalize_grant_role(role)
    normalized_subject_type = (subject_type or '').strip().lower()
    if normalized_subject_type not in {'user_id', 'username'}:
        raise HTTPException(status_code=400, detail='Invalid grant subject type')
    normalized_subject_id = (subject_id or '').strip()
    if not normalized_subject_id:
        raise HTTPException(status_code=400, detail='Grant subject id is required')

    stamp = now or time.time()
    grant = (
        db.query(HorizonProjectGrant)
        .filter(HorizonProjectGrant.project_id == project_id)
        .filter(HorizonProjectGrant.subject_type == normalized_subject_type)
        .filter(HorizonProjectGrant.subject_id == normalized_subject_id)
        .first()
    )
    if grant is None:
        grant = HorizonProjectGrant(
            id=str(uuid.uuid4()),
            project_id=project_id,
            subject_type=normalized_subject_type,
            subject_id=normalized_subject_id,
            role=normalized_role,
            created_at=stamp,
            updated_at=stamp,
        )
    else:
        existing_rank = ROLE_RANK.get(grant.role, 0)
        next_rank = ROLE_RANK.get(normalized_role, 0)
        if not allow_downgrade and existing_rank > next_rank:
            return grant
        grant.role = normalized_role
        grant.updated_at = stamp
    db.add(grant)
    return grant


def ensure_horizon_project_membership_for_user(
    db: Session,
    *,
    project_id: str,
    user_ref: str | None,
    role: str = 'viewer',
    allow_downgrade: bool = False,
) -> dict:
    from .projects import get_horizon_project

    user = get_horizon_assignable_user(user_ref)
    if user is None:
        raise HTTPException(status_code=400, detail='Assignable team account not found')

    now = time.time()
    resolved_role = _normalize_grant_role(role)
    for subject_type, subject_id in _subject_candidates_for_user(user):
        grant = _upsert_horizon_project_grant(
            db,
            project_id=project_id,
            subject_type=subject_type,
            subject_id=subject_id,
            role=role,
            now=now,
            allow_downgrade=allow_downgrade,
        )
        if ROLE_RANK.get(grant.role, 0) > ROLE_RANK.get(resolved_role, 0):
            resolved_role = grant.role

    project = get_horizon_project(db, project_id)
    project.updated_at = now
    db.add(project)
    workspace_path = ensure_horizon_project_user_workspace(db, project_id, user)
    db.commit()

    return {
        'user': user,
        'workspace_path': workspace_path,
        'role': resolved_role,
    }


def remove_horizon_project_membership_for_user(db: Session, *, project_id: str, user_ref: str | None) -> dict:
    from .projects import revoke_horizon_project_access

    user = get_horizon_assignable_user(user_ref)
    if user is None:
        raise HTTPException(status_code=404, detail='Project member not found')

    canonical_user_id = _canonical_user_id(user)
    if not canonical_user_id:
        raise HTTPException(status_code=404, detail='Project member not found')

    assigned_shots = (
        db.query(HorizonShot)
        .join(HorizonShotAssignee, HorizonShotAssignee.shot_id == HorizonShot.id)
        .filter(HorizonShot.project_id == project_id)
        .filter(HorizonShotAssignee.user_id == canonical_user_id)
        .order_by(HorizonShot.shot_code.asc())
        .all()
    )
    if assigned_shots:
        shot_codes = [shot.shot_code for shot in assigned_shots]
        raise HTTPException(
            status_code=409,
            detail={
                'code': 'member_has_assigned_shots',
                'message': 'Cannot remove team member while shots are still assigned.',
                'user_id': canonical_user_id,
                'assigned_shot_count': len(shot_codes),
                'assigned_shot_codes': shot_codes[:10],
            },
        )

    removed = False
    for subject_type, subject_id in _subject_candidates_for_user(user):
        removed = revoke_horizon_project_access(db, project_id=project_id, subject_type=subject_type, subject_id=subject_id) or removed

    if not removed:
        raise HTTPException(status_code=404, detail='Project member not found')

    return {
        'removed': True,
        'user_id': canonical_user_id,
        'workspace_path': get_horizon_user_workspace_path(user),
    }


def serialize_horizon_shot_assignee(shot: HorizonShot) -> dict | None:
    # Compatibility bridge: horizons_shot_assignees is the canonical
    # multi-assignee source. We still expose legacy assignee_user_id/assignee
    # fields for older frontends, deployed lanes, and agent skills that expect
    # a single owner. Purge this helper and the legacy column after all clients
    # have moved to assignee_user_ids/assignees.
    assignees = serialize_horizon_shot_assignees(shot)
    return assignees[0] if assignees else None


def _role_meets(required_role: str, actual_role: str | None) -> bool:
    if not actual_role:
        return False
    return ROLE_RANK.get(actual_role, 0) >= ROLE_RANK.get(required_role, 0)
