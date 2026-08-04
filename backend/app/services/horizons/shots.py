from __future__ import annotations

import time
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    HorizonShot,
    HorizonShotAssignee,
    HorizonShotVersion,
    HorizonTracker,
    MediaAsset,
)

from .common import _dedupe_ordered, _normalize_shot_status
from .projects import get_horizon_project, require_horizon_project_writable
from .team import _ensure_horizon_project_memberships_for_assignees, _resolve_horizon_assignee_ids, _shot_assignee_rows, _subject_candidates_for_user, get_horizon_shot_assignee_ids, is_restricted_horizon_artist
from .trackers import get_horizon_tracker, get_horizon_tracker_by_ref
from .version_publication import initial_version_publication, set_version_share_state, version_is_published, version_media_is_publishable

def list_horizon_shots(db: Session, project_id: str, tracker_id: str | None = None, *, include_archived: bool = False) -> list[HorizonShot]:
    get_horizon_project(db, project_id)
    query = db.query(HorizonShot).filter(HorizonShot.project_id == project_id)
    if tracker_id:
        query = query.filter(HorizonShot.tracker_id == tracker_id)
    if not include_archived:
        query = query.filter(HorizonShot.archived_at.is_(None))
    return query.order_by(HorizonShot.created_at.asc()).all()


def list_visible_horizon_shots(
    db: Session,
    project_id: str,
    *,
    tracker_id: str | None = None,
    user: dict | None = None,
    access_role: str | None = None,
    include_archived: bool = False,
) -> list[HorizonShot]:
    query = db.query(HorizonShot).filter(HorizonShot.project_id == project_id)
    if tracker_id:
        query = query.filter(HorizonShot.tracker_id == tracker_id)
    if not include_archived:
        query = query.filter(HorizonShot.archived_at.is_(None))
    if is_restricted_horizon_artist(user, access_role):
        subject_ids = {value for _stype, value in _subject_candidates_for_user(user)}
        if not subject_ids:
            return []
        query = (
            query
            .join(HorizonShotAssignee, HorizonShotAssignee.shot_id == HorizonShot.id)
            .filter(HorizonShotAssignee.user_id.in_(subject_ids))
            .distinct()
        )
    return query.order_by(HorizonShot.created_at.asc()).all()


def get_horizon_shot(db: Session, project_id: str, shot_id: str) -> HorizonShot:
    shot = (
        db.query(HorizonShot)
        .filter(HorizonShot.id == shot_id)
        .filter(HorizonShot.project_id == project_id)
        .first()
    )
    if not shot:
        raise HTTPException(status_code=404, detail='Horizons shot not found')
    return shot


def get_horizon_shot_by_ref(db: Session, project_id: str, shot_ref: str, *, tracker_id: str | None = None) -> HorizonShot:
    normalized_ref = (shot_ref or '').strip()
    if not normalized_ref:
        raise HTTPException(status_code=404, detail='Shot not found')

    query = db.query(HorizonShot).filter(HorizonShot.project_id == project_id)
    if tracker_id:
        query = query.filter(HorizonShot.tracker_id == tracker_id)

    shot = query.filter(HorizonShot.id == normalized_ref).first()
    if shot:
        return shot

    code_matches = query.filter(HorizonShot.shot_code == normalized_ref).order_by(HorizonShot.created_at.asc()).limit(2).all()
    if len(code_matches) == 1:
        return code_matches[0]
    if len(code_matches) > 1:
        raise HTTPException(status_code=409, detail='Shot code is ambiguous; use the shot id')
    raise HTTPException(status_code=404, detail='Shot not found')


def require_horizon_shot_view_access(db: Session, project_id: str, shot_id: str, *, tracker_id: str | None = None, user: dict | None = None, access_role: str | None = None) -> HorizonShot:
    shot = get_horizon_shot_by_ref(db, project_id, shot_id, tracker_id=tracker_id)
    if is_restricted_horizon_artist(user, access_role):
        subject_ids = {value for _stype, value in _subject_candidates_for_user(user)}
        if not set(get_horizon_shot_assignee_ids(shot, db)).intersection(subject_ids):
            raise HTTPException(status_code=404, detail='Horizons shot not found')
    return shot


def require_horizon_tracker_view_access(db: Session, project_id: str, tracker_ref: str, *, user: dict | None = None, access_role: str | None = None) -> HorizonTracker:
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_ref)
    if is_restricted_horizon_artist(user, access_role):
        visible_shots = list_visible_horizon_shots(db, project_id, tracker_id=tracker.id, user=user, access_role=access_role)
        if not visible_shots:
            raise HTTPException(status_code=404, detail='Horizons tracker not found')
    return tracker


def set_horizon_shot_assignees(
    db: Session,
    shot: HorizonShot,
    assignee_user_ids: list[str | None] | None,
    *,
    assigned_by: str | None = None,
) -> dict:
    next_ids = _resolve_horizon_assignee_ids(assignee_user_ids)
    existing_rows = _shot_assignee_rows(db, shot)
    existing_ids = _dedupe_ordered([row.user_id for row in existing_rows if row.user_id])
    if not existing_ids and shot.assignee_user_id:
        existing_ids = _dedupe_ordered([shot.assignee_user_id])

    existing_set = set(existing_ids)
    next_set = set(next_ids)

    for row in existing_rows:
        if row.user_id not in next_set:
            db.delete(row)

    existing_rows_by_user = {row.user_id: row for row in existing_rows}
    now = time.time()
    for index, user_id in enumerate(next_ids):
        existing_row = existing_rows_by_user.get(user_id)
        if existing_row:
            existing_row.sort_order = index
            existing_row.updated_at = now
            db.add(existing_row)
            continue
        db.add(HorizonShotAssignee(
            id=str(uuid.uuid4()),
            project_id=shot.project_id,
            tracker_id=shot.tracker_id,
            shot_id=shot.id,
            user_id=user_id,
            sort_order=index,
            created_by=assigned_by,
            created_at=now,
            updated_at=now,
        ))

    _ensure_horizon_project_memberships_for_assignees(db, project_id=shot.project_id, user_ids=next_ids)
    shot.assignee_user_id = next_ids[0] if next_ids else None
    shot.updated_at = now
    db.add(shot)
    return {
        'old_ids': existing_ids,
        'new_ids': next_ids,
        'added_ids': [user_id for user_id in next_ids if user_id not in existing_set],
        'removed_ids': [user_id for user_id in existing_ids if user_id not in next_set],
    }


def create_horizon_shot(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    shot_code: str,
    description: str | None = None,
    status: str | None = None,
    category: str | None = None,
    assignee_user_id: str | None = None,
    assignee_user_ids: list[str | None] | None = None,
) -> HorizonShot:
    shot = _create_horizon_shot_no_commit(
        db,
        project_id=project_id,
        tracker_id=tracker_id,
        shot_code=shot_code,
        description=description,
        status=status,
        category=category,
        assignee_user_id=assignee_user_id,
        assignee_user_ids=assignee_user_ids,
    )
    db.commit()
    db.refresh(shot)
    return shot


def _create_horizon_shot_no_commit(
    db: Session,
    *,
    project_id: str,
    tracker_id: str,
    shot_code: str,
    description: str | None = None,
    status: str | None = None,
    category: str | None = None,
    assignee_user_id: str | None = None,
    assignee_user_ids: list[str | None] | None = None,
) -> HorizonShot:
    tracker = get_horizon_tracker_by_ref(db, project_id, tracker_id)
    project = get_horizon_project(db, project_id)
    normalized_code = (shot_code or '').strip()
    if not normalized_code:
        raise HTTPException(status_code=400, detail='Shot code is required')
    if (
        db.query(HorizonShot)
        .filter(HorizonShot.tracker_id == tracker.id)
        .filter(HorizonShot.shot_code == normalized_code)
        .first()
    ):
        raise HTTPException(status_code=400, detail='Shot code already exists in tracker')

    now = time.time()
    assignment_ids = _resolve_horizon_assignee_ids(assignee_user_ids if assignee_user_ids is not None else [assignee_user_id])

    shot = HorizonShot(
        id=str(uuid.uuid4()),
        project_id=project_id,
        tracker_id=tracker_id,
        shot_code=normalized_code,
        description=description,
        status=_normalize_shot_status(status),
        category=category,
        assignee_user_id=assignment_ids[0] if assignment_ids else None,
        created_at=now,
        updated_at=now,
    )
    tracker.updated_at = now
    project.updated_at = now
    db.add(tracker)
    db.add(project)
    db.add(shot)
    db.flush()
    set_horizon_shot_assignees(db, shot, assignment_ids)
    return shot


def update_horizon_shot(
    db: Session,
    project_id: str,
    shot_ref: str,
    *,
    shot_code: str | None = None,
    description: str | None = None,
    status: str | None = None,
    category: str | None = None,
    assignee_user_id: str | None = None,
    assignee_user_ids: list[str | None] | None = None,
    fields_set: set[str] | None = None,
) -> HorizonShot:
    shot = _update_horizon_shot_no_commit(
        db,
        project_id,
        shot_ref,
        shot_code=shot_code,
        description=description,
        status=status,
        category=category,
        assignee_user_id=assignee_user_id,
        assignee_user_ids=assignee_user_ids,
        fields_set=fields_set,
    )
    db.commit()
    db.refresh(shot)
    return shot


def _update_horizon_shot_no_commit(
    db: Session,
    project_id: str,
    shot_ref: str,
    *,
    shot_code: str | None = None,
    description: str | None = None,
    status: str | None = None,
    category: str | None = None,
    assignee_user_id: str | None = None,
    assignee_user_ids: list[str | None] | None = None,
    fields_set: set[str] | None = None,
) -> HorizonShot:
    shot = get_horizon_shot_by_ref(db, project_id, shot_ref)
    tracker = get_horizon_tracker(db, project_id, shot.tracker_id)
    project = get_horizon_project(db, project_id)
    fields = set(fields_set or set())

    if 'shot_code' in fields:
        normalized_code = (shot_code or '').strip()
        if not normalized_code:
            raise HTTPException(status_code=400, detail='Shot code is required')
        existing = (
            db.query(HorizonShot)
            .filter(HorizonShot.tracker_id == shot.tracker_id)
            .filter(HorizonShot.shot_code == normalized_code)
            .first()
        )
        if existing and existing.id != shot.id:
            raise HTTPException(status_code=400, detail='Shot code already exists in tracker')
        shot.shot_code = normalized_code
    if 'description' in fields:
        shot.description = description
    if 'status' in fields:
        shot.status = _normalize_shot_status(status)
    if 'category' in fields:
        shot.category = category
    if 'assignee_user_id' in fields:
        set_horizon_shot_assignees(db, shot, [assignee_user_id] if assignee_user_id else [])
    if 'assignee_user_ids' in fields:
        set_horizon_shot_assignees(db, shot, assignee_user_ids or [])

    now = time.time()
    shot.updated_at = now
    tracker.updated_at = now
    project.updated_at = now
    db.add(shot)
    db.add(tracker)
    db.add(project)
    return shot


def list_horizon_shot_versions(db: Session, project_id: str, shot_id: str) -> list[HorizonShotVersion]:
    shot = get_horizon_shot_by_ref(db, project_id, shot_id)
    return (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.shot_id == shot.id)
        .order_by(HorizonShotVersion.created_at.asc())
        .all()
    )


def create_horizon_shot_version(db: Session, *, project_id: str, shot_id: str, label: str, media_asset_id: str | None = None, notes: str | None = None, created_by: str | None = None) -> HorizonShotVersion:
    version = _create_horizon_shot_version_no_commit(
        db,
        project_id=project_id,
        shot_id=shot_id,
        label=label,
        media_asset_id=media_asset_id,
        notes=notes,
        created_by=created_by,
    )
    db.commit()
    db.refresh(version)
    return version


def _create_horizon_shot_version_no_commit(db: Session, *, project_id: str, shot_id: str, label: str, media_asset_id: str | None = None, notes: str | None = None, created_by: str | None = None) -> HorizonShotVersion:
    require_horizon_project_writable(db, project_id)
    shot = get_horizon_shot_by_ref(db, project_id, shot_id)
    tracker = get_horizon_tracker(db, project_id, shot.tracker_id)
    project = get_horizon_project(db, project_id)
    normalized_label = (label or '').strip()
    if not normalized_label:
        raise HTTPException(status_code=400, detail='Version label is required')
    if (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.shot_id == shot.id)
        .filter(HorizonShotVersion.label == normalized_label)
        .first()
    ):
        raise HTTPException(status_code=400, detail='Version label already exists on shot')

    asset = None
    if media_asset_id:
        asset = (
            db.query(MediaAsset)
            .filter(MediaAsset.id == media_asset_id)
            .filter(MediaAsset.project_id == project_id)
            .first()
        )
        if not asset:
            raise HTTPException(status_code=400, detail='Media asset not found for project')

    now = time.time()
    share_state, published_at = initial_version_publication(tracker, now=now)
    if share_state == 'published' and not version_media_is_publishable(db, project_id, asset.id if asset else None):
        share_state, published_at = 'internal', None
    version = HorizonShotVersion(
        id=str(uuid.uuid4()),
        project_id=project_id,
        tracker_id=shot.tracker_id,
        shot_id=shot.id,
        label=normalized_label,
        media_asset_id=asset.id if asset else None,
        notes=notes,
        share_state=share_state,
        published_at=published_at,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    shot.latest_version_label = normalized_label
    shot.latest_media_asset_id = asset.id if asset else None
    shot.updated_at = now
    tracker.updated_at = now
    project.updated_at = now
    db.add(shot)
    db.add(tracker)
    db.add(project)
    db.flush()
    if version_is_published(version):
        set_version_share_state(db, version, 'published', now=now)
    return version


def update_horizon_shot_version(
    db: Session,
    project_id: str,
    shot_ref: str,
    version_id: str,
    *,
    media_asset_id: str | None = None,
    notes: str | None = None,
    fields_set: set[str] | None = None,
) -> HorizonShotVersion:
    version = _update_horizon_shot_version_no_commit(
        db,
        project_id,
        shot_ref,
        version_id,
        media_asset_id=media_asset_id,
        notes=notes,
        fields_set=fields_set,
    )
    db.commit()
    db.refresh(version)
    return version


def _update_horizon_shot_version_no_commit(
    db: Session,
    project_id: str,
    shot_ref: str,
    version_id: str,
    *,
    media_asset_id: str | None = None,
    notes: str | None = None,
    fields_set: set[str] | None = None,
) -> HorizonShotVersion:
    shot = get_horizon_shot_by_ref(db, project_id, shot_ref)
    tracker = get_horizon_tracker(db, project_id, shot.tracker_id)
    project = get_horizon_project(db, project_id)
    version = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.id == version_id)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.shot_id == shot.id)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail='Horizons version not found')

    fields = set(fields_set or set())
    asset = None
    if 'media_asset_id' in fields:
        if version_is_published(version) and media_asset_id != version.media_asset_id:
            raise HTTPException(
                status_code=409,
                detail='Published version media cannot be replaced; add a new version instead',
            )
        if media_asset_id:
            asset = (
                db.query(MediaAsset)
                .filter(MediaAsset.id == media_asset_id)
                .filter(MediaAsset.project_id == project_id)
                .first()
            )
            if not asset:
                raise HTTPException(status_code=400, detail='Media asset not found for project')
            version.media_asset_id = asset.id
        else:
            version.media_asset_id = None
    if 'notes' in fields:
        version.notes = notes

    now = time.time()
    version.updated_at = now
    if shot.latest_version_label == version.label:
        shot.latest_media_asset_id = version.media_asset_id
        shot.updated_at = now
        db.add(shot)
    tracker.updated_at = now
    project.updated_at = now
    db.add(version)
    db.add(tracker)
    db.add(project)
    db.flush()
    return version
