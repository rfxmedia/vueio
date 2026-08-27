from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    HorizonProject,
    HorizonProjectGrant,
    HorizonShot,
    HorizonShotVersion,
    HorizonTracker,
    MediaAsset,
)
from app.services.naming import slugify
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.projects import (
    configured_project_storage_roots,
    get_project_dir,
    normalize_project_storage_path,
    project_storage_is_read_only,
    resolve_project_root,
    resolve_storage_location,
    storage_location_is_read_only,
)

from .common import DELETED_PROJECT_STATUS, ROLE_RANK, _normalize_project_status, _normalize_visibility, is_deleted_horizon_project

def _unique_horizon_project_slug(db: Session, base_slug: str) -> str:
    base = base_slug[:80].strip('-') or f'project-{uuid.uuid4().hex[:8]}'
    candidate = base
    counter = 2
    while db.query(HorizonProject).filter(HorizonProject.slug == candidate).first():
        suffix = f'-{counter}'
        candidate = f'{base[:80 - len(suffix)].strip("-")}{suffix}'
        counter += 1
    return candidate


def _new_horizon_project_id(db: Session, slug: str) -> str:
    # Runtime folders live at DATA_DIR/projects/<project_id>. For new Horizons
    # projects, make that stable ID readable for NAS/File Explorer browsing while
    # keeping old UUID IDs untouched and valid.
    base = slugify(slug, f'project-{uuid.uuid4().hex[:8]}')[:80].strip('-') or f'project-{uuid.uuid4().hex[:8]}'
    for _ in range(10):
        candidate = f'{base}--{uuid.uuid4().hex[:8]}'
        project_dir = get_project_dir(candidate)
        if not db.query(HorizonProject).filter(HorizonProject.id == candidate).first() and not project_dir.exists():
            return candidate
    return f'{base}--{uuid.uuid4().hex}'


def list_horizon_projects(db: Session, *, include_deleted: bool = False) -> list[HorizonProject]:
    query = db.query(HorizonProject)
    if not include_deleted:
        query = query.filter(HorizonProject.status != DELETED_PROJECT_STATUS)
    return query.order_by(HorizonProject.created_at.asc()).all()


def serialize_horizon_project(db: Session, project: HorizonProject, user: dict | None = None, access_role: str | None = None) -> dict:
    from .shots import list_visible_horizon_shots
    from .team import is_restricted_horizon_artist

    if access_role is None and user is not None:
        access_role = get_horizon_project_access_role(db, project, user)

    if is_restricted_horizon_artist(user, access_role):
        visible_shots = list_visible_horizon_shots(db, project.id, user=user, access_role=access_role)
        visible_shot_ids = [shot.id for shot in visible_shots]
        tracker_count = len({shot.tracker_id for shot in visible_shots})
        shot_count = len(visible_shots)
        version_count = (
            db.query(func.count(HorizonShotVersion.id))
            .filter(HorizonShotVersion.project_id == project.id)
            .filter(HorizonShotVersion.shot_id.in_(visible_shot_ids))
            .scalar() or 0
        ) if visible_shot_ids else 0
    else:
        tracker_count = db.query(func.count(HorizonTracker.id)).filter(HorizonTracker.project_id == project.id).scalar() or 0
        shot_count = db.query(func.count(HorizonShot.id)).filter(HorizonShot.project_id == project.id).scalar() or 0
        version_count = db.query(func.count(HorizonShotVersion.id)).filter(HorizonShotVersion.project_id == project.id).scalar() or 0

    unavailable_asset_count = (
        db.query(func.count(MediaAsset.id))
        .filter(MediaAsset.project_id == project.id)
        .filter(MediaAsset.unavailable_at.isnot(None))
        .filter(MediaAsset.unavailable_reason != 'duplicate_active_generation')
        .scalar() or 0
    )

    return {
        'id': project.id,
        'slug': project.slug,
        'title': project.title,
        'description': project.description,
        'status': project.status,
        'visibility': project.visibility,
        'created_by': project.created_by,
        'created_at': project.created_at,
        'updated_at': project.updated_at,
        'due_date': project.due_date,
        'thumbnail_path': project.thumbnail_path,
        'storage_root': project.storage_root or 'data',
        'storage_path': project.storage_path or project.id,
        'storage_read_only': project_storage_is_read_only(project),
        'uses_internal_storage': (project.storage_root or 'data') == 'data',
        'tracker_count': int(tracker_count),
        'shot_count': int(shot_count),
        'version_count': int(version_count),
        'unavailable_asset_count': int(unavailable_asset_count),
        'has_offline_media': bool(unavailable_asset_count),
        'source': 'horizons_db',
        'access_role': access_role,
    }


def list_horizon_project_summaries(db: Session) -> list[dict]:
    return [serialize_horizon_project(db, project) for project in list_horizon_projects(db)]


def list_unavailable_project_media(db: Session, project_id: str, *, limit: int = 100) -> dict:
    query = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.unavailable_at.isnot(None))
        .filter(MediaAsset.unavailable_reason != 'duplicate_active_generation')
        .order_by(MediaAsset.file_path.asc())
    )
    total = query.count()
    assets = query.limit(limit).all()
    asset_ids = [asset.id for asset in assets]
    references = {asset_id: [] for asset_id in asset_ids}
    seen_references = {asset_id: set() for asset_id in asset_ids}

    if asset_ids:
        version_rows = (
            db.query(HorizonShotVersion, HorizonShot, HorizonTracker)
            .join(HorizonShot, HorizonShot.id == HorizonShotVersion.shot_id)
            .join(HorizonTracker, HorizonTracker.id == HorizonShotVersion.tracker_id)
            .filter(HorizonShotVersion.project_id == project_id)
            .filter(HorizonShotVersion.media_asset_id.in_(asset_ids))
            .all()
        )
        for version, shot, tracker in version_rows:
            reference_key = (tracker.id, shot.id, version.id)
            if reference_key in seen_references[version.media_asset_id]:
                continue
            seen_references[version.media_asset_id].add(reference_key)
            references[version.media_asset_id].append({
                'tracker_id': tracker.id,
                'tracker_name': tracker.name,
                'shot_id': shot.id,
                'shot_code': shot.shot_code,
                'version_id': version.id,
                'version_label': version.label,
            })

        latest_rows = (
            db.query(HorizonShot, HorizonTracker)
            .join(HorizonTracker, HorizonTracker.id == HorizonShot.tracker_id)
            .filter(HorizonShot.project_id == project_id)
            .filter(HorizonShot.latest_media_asset_id.in_(asset_ids))
            .all()
        )
        for shot, tracker in latest_rows:
            if any(reference['shot_id'] == shot.id for reference in references[shot.latest_media_asset_id]):
                continue
            reference_key = (tracker.id, shot.id, None)
            if reference_key in seen_references[shot.latest_media_asset_id]:
                continue
            seen_references[shot.latest_media_asset_id].add(reference_key)
            references[shot.latest_media_asset_id].append({
                'tracker_id': tracker.id,
                'tracker_name': tracker.name,
                'shot_id': shot.id,
                'shot_code': shot.shot_code,
                'version_id': None,
                'version_label': shot.latest_version_label,
            })

    return {
        'total': total,
        'items': [{
            'asset_id': asset.id,
            'file_path': asset.file_path,
            'file_name': Path(asset.file_path).name,
            'storage_scope': asset.storage_scope,
            'unavailable_reason': asset.unavailable_reason,
            'references': references[asset.id],
        } for asset in assets],
    }


def get_horizon_project(db: Session, project_id: str, *, include_deleted: bool = False) -> HorizonProject:
    project = db.query(HorizonProject).filter(HorizonProject.id == project_id).first()
    if not project or (is_deleted_horizon_project(project) and not include_deleted):
        raise HTTPException(status_code=404, detail='Horizons project not found')
    return project


def get_horizon_project_access_role(db: Session, project: HorizonProject, user: dict, auth_mode: str | None = None) -> str | None:
    from .team import _subject_candidates_for_user

    if is_deleted_horizon_project(project):
        return None
    if user.get('role') == 'admin':
        return 'admin'

    owner_candidates = {value for _stype, value in _subject_candidates_for_user(user)}
    if project.created_by and project.created_by in owner_candidates:
        return 'owner'

    explicit_roles = []
    for subject_type, subject_id in _subject_candidates_for_user(user):
        grant = (
            db.query(HorizonProjectGrant)
            .filter(HorizonProjectGrant.project_id == project.id)
            .filter(HorizonProjectGrant.subject_type == subject_type)
            .filter(HorizonProjectGrant.subject_id == subject_id)
            .first()
        )
        if grant:
            explicit_roles.append(grant.role)
    if explicit_roles:
        explicit_roles.sort(key=lambda value: ROLE_RANK.get(value, 0), reverse=True)
        return explicit_roles[0]

    return None


def require_horizon_project_access(db: Session, project_id: str, user: dict, auth_mode: str | None = None, required_role: str = 'viewer') -> tuple[HorizonProject, str]:
    from .team import _role_meets

    project = get_horizon_project(db, project_id)
    role = get_horizon_project_access_role(db, project, user, auth_mode=auth_mode)
    if not _role_meets(required_role, role):
        raise HTTPException(status_code=403, detail='Horizons project access required')
    return project, role or required_role


def list_visible_horizon_projects(db: Session, user: dict, auth_mode: str | None = None) -> list[HorizonProject]:
    if user.get('role') == 'admin':
        return list_horizon_projects(db)
    visible = []
    for project in list_horizon_projects(db):
        if get_horizon_project_access_role(db, project, user, auth_mode=auth_mode):
            visible.append(project)
    return visible


def list_visible_horizon_project_summaries(db: Session, user: dict, auth_mode: str | None = None) -> list[dict]:
    return [serialize_horizon_project(db, project, user=user) for project in list_visible_horizon_projects(db, user, auth_mode=auth_mode)]


def list_horizon_project_grants(db: Session, project_id: str) -> list[HorizonProjectGrant]:
    return (
        db.query(HorizonProjectGrant)
        .filter(HorizonProjectGrant.project_id == project_id)
        .order_by(HorizonProjectGrant.created_at.asc())
        .all()
    )


def grant_horizon_project_access(db: Session, *, project_id: str, subject_type: str, subject_id: str, role: str) -> HorizonProjectGrant:
    from .team import _upsert_horizon_project_grant

    grant = _upsert_horizon_project_grant(
        db,
        project_id=project_id,
        subject_type=subject_type,
        subject_id=subject_id,
        role=role,
    )
    db.commit()
    db.refresh(grant)
    return grant


def revoke_horizon_project_access(db: Session, *, project_id: str, subject_type: str, subject_id: str) -> bool:
    normalized_subject_type = (subject_type or '').strip().lower()
    normalized_subject_id = (subject_id or '').strip()
    grant = (
        db.query(HorizonProjectGrant)
        .filter(HorizonProjectGrant.project_id == project_id)
        .filter(HorizonProjectGrant.subject_type == normalized_subject_type)
        .filter(HorizonProjectGrant.subject_id == normalized_subject_id)
        .first()
    )
    if grant is None:
        return False
    db.delete(grant)
    db.commit()
    return True


def create_horizon_project(
    db: Session,
    *,
    title: str,
    slug: str | None = None,
    description: str | None = None,
    due_date: str | None = None,
    thumbnail_path: str | None = None,
    status: str | None = None,
    visibility: str | None = None,
    created_by: str | None = None,
    storage_root: str | None = None,
    storage_path: str | None = None,
) -> HorizonProject:
    now = time.time()
    normalized_slug = slugify(slug or title, f'project-{str(uuid.uuid4())[:8]}')
    existing_slug = db.query(HorizonProject).filter(HorizonProject.slug == normalized_slug).first()
    if existing_slug:
        if slug:
            raise HTTPException(status_code=400, detail='Horizons project slug already exists')
        normalized_slug = _unique_horizon_project_slug(db, normalized_slug)

    project_id = _new_horizon_project_id(db, normalized_slug)
    requested_root = str(storage_root or 'data').strip().lower()
    final_storage_path = project_id
    target: Path
    use_existing_project_folder = False
    if requested_root != 'data':
        configured_roots = configured_project_storage_roots()
        if requested_root not in configured_roots:
            raise HTTPException(status_code=400, detail='Choose a configured project storage location')
        if not configured_roots[requested_root].is_dir():
            raise HTTPException(status_code=409, detail='Selected storage location is unavailable')
        final_storage_path = normalize_project_storage_path(storage_path)
        target = resolve_storage_location(requested_root, final_storage_path)
        if target.exists() and not target.is_dir():
            raise HTTPException(status_code=409, detail='Selected project folder is not a folder')
        use_existing_project_folder = target.is_dir()
        claimed = db.query(HorizonProject.id).filter(
            HorizonProject.storage_root == requested_root,
            HorizonProject.storage_path == final_storage_path,
        ).first()
        if claimed:
            raise HTTPException(status_code=409, detail='This folder is already used by another project')
    else:
        target = resolve_storage_location(requested_root, final_storage_path)

    project = HorizonProject(
        id=project_id,
        slug=normalized_slug,
        title=(title or '').strip(),
        description=description,
        status=_normalize_project_status(status),
        visibility=_normalize_visibility(visibility),
        created_by=created_by,
        created_at=now,
        updated_at=now,
        due_date=due_date,
        thumbnail_path=thumbnail_path,
        storage_root=requested_root,
        storage_path=final_storage_path,
    )
    if not project.title:
        raise HTTPException(status_code=400, detail='Project title is required')

    if storage_location_is_read_only(target):
        raise HTTPException(status_code=409, detail='Selected storage location is read-only')
    created_project_dir = False
    try:
        if not use_existing_project_folder:
            target.mkdir(parents=True, exist_ok=False)
            created_project_dir = True
        make_project_path_smb_mutable(target)
    except FileExistsError:
        # A concurrent creator won the same external folder name after the
        # availability check. Reusing it could mix two projects.
        raise HTTPException(status_code=409, detail='The selected project folder was created by another request')
    except OSError as exc:
        if created_project_dir:
            try:
                target.rmdir()
            except OSError:
                pass
        raise HTTPException(status_code=409, detail='Unable to create the selected project folder') from exc

    try:
        db.add(project)
        db.commit()
    except Exception:
        db.rollback()
        if created_project_dir:
            try:
                target.rmdir()
            except OSError:
                # Never remove a directory after another process has placed
                # content inside it.
                pass
        raise
    db.refresh(project)

    if created_by:
        for subject_type in ('user_id', 'username'):
            try:
                grant_horizon_project_access(db, project_id=project.id, subject_type=subject_type, subject_id=str(created_by), role='owner')
            except Exception:
                pass

    return project


def update_horizon_project(
    db: Session,
    project_id: str,
    *,
    title: str | None = None,
    slug: str | None = None,
    description: str | None = None,
    due_date: str | None = None,
    thumbnail_path: str | None = None,
    status: str | None = None,
    visibility: str | None = None,
    fields_set: set[str] | None = None,
) -> HorizonProject:
    project = get_horizon_project(db, project_id)
    fields = set(fields_set or set())

    if 'title' in fields:
        normalized_title = (title or '').strip()
        if not normalized_title:
            raise HTTPException(status_code=400, detail='Project title is required')
        project.title = normalized_title
    if 'slug' in fields:
        normalized_slug = slugify(slug or project.title, f'project-{str(uuid.uuid4())[:8]}')
        existing = db.query(HorizonProject).filter(HorizonProject.slug == normalized_slug).first()
        if existing and existing.id != project.id:
            raise HTTPException(status_code=400, detail='Horizons project slug already exists')
        project.slug = normalized_slug
    if 'description' in fields:
        project.description = description
    if 'due_date' in fields:
        project.due_date = due_date
    if 'thumbnail_path' in fields:
        project.thumbnail_path = thumbnail_path
    if 'status' in fields:
        project.status = _normalize_project_status(status)
    if 'visibility' in fields:
        project.visibility = _normalize_visibility(visibility)

    project.updated_at = time.time()
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def ensure_horizon_project_runtime_dir(db: Session, project_id: str) -> Path:
    project = get_horizon_project(db, project_id)
    project_dir = resolve_project_root(project)
    if project_storage_is_read_only(project):
        raise HTTPException(status_code=409, detail='This project storage location is read-only')
    project_dir.mkdir(parents=True, exist_ok=True)
    make_project_path_smb_mutable(project_dir)
    return project_dir


def require_horizon_project_writable(db: Session, project_id: str) -> HorizonProject:
    project = get_horizon_project(db, project_id)
    if project_storage_is_read_only(project):
        raise HTTPException(status_code=409, detail='This project storage location is read-only')
    return project


def touch_horizon_project(
    db: Session,
    project_id: str,
    *,
    commit: bool = True,
) -> HorizonProject:
    project = get_horizon_project(db, project_id)
    project.updated_at = time.time()
    db.add(project)
    if commit:
        db.commit()
        db.refresh(project)
    else:
        db.flush()
    return project
