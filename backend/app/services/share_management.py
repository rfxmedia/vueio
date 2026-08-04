from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models import ShareLink
from app.services.horizon_pages import get_horizon_page_by_ref
from app.services.horizons_fresh import get_horizon_project, get_horizon_tracker_for_share
from app.services.share_access import hash_share_password


def serialize_share_for_management(share: ShareLink, db: Session, project_cache: dict[str, object | None] | None = None) -> dict:
    target_name = ''
    tracker_name = share.tracker_name
    project = _get_cached_project(db, share.project_id, project_cache)

    if share.project_id:
        if project:
            try:
                if share.share_type == 'tracker' and (share.tracker_id or share.tracker_name):
                    tracker = get_horizon_tracker_for_share(db, share)
                    tracker_name = tracker.name
                    target_name = f'{project.title} / {tracker.name}'
                elif share.share_type == 'page' and share.page_id:
                    page = get_horizon_page_by_ref(db, share.project_id, share.page_id)
                    target_name = f'{project.title} / {page.title}'
                elif share.share_type == 'project':
                    target_name = project.title
            except Exception:
                target_name = project.title
        else:
            if share.share_type == 'tracker' and share.tracker_name:
                target_name = f'[Deleted] {share.tracker_name}'
            elif share.share_type == 'page' and share.page_id:
                target_name = f'[Deleted Page: {share.page_id}]'
            elif share.share_type == 'project':
                target_name = f'[Deleted Project: {share.project_id}]'

    if not target_name and share.path:
        target_name = Path(share.path).name

    return {
        'id': share.id,
        'share_type': share.share_type or ('folder' if share.is_folder else 'file'),
        'path': share.path,
        'project_id': share.project_id,
        'project_title': project.title if project else '',
        'project_status': project.status if project else '',
        'project_thumbnail_path': project.thumbnail_path if project else '',
        'tracker_id': share.tracker_id,
        'tracker_name': tracker_name,
        'page_id': share.page_id,
        'target_name': target_name,
        'created_by': share.created_by,
        'created_at': share.created_at,
        'expires_at': share.expires_at,
        'has_password': share.password_hash is not None,
        'is_active': share.is_active,
        'access_count': share.access_count or 0,
        'last_accessed': share.last_accessed,
        'allow_download': share.allow_download,
        'allow_upload': share.allow_upload,
        'request_files': share.request_files,
    }


def apply_share_management_update(
    share: ShareLink,
    *,
    expires_at: float | None = None,
    password: str | None = None,
    is_active: bool | None = None,
    allow_download: bool | None = None,
    allow_upload: bool | None = None,
) -> None:
    if expires_at is not None:
        share.expires_at = expires_at if expires_at > 0 else None
    if password is not None:
        share.password_hash = hash_share_password(password)
    if is_active is not None:
        share.is_active = is_active
    if allow_download is not None:
        share.allow_download = allow_download
    if allow_upload is not None:
        share.allow_upload = True if share.request_files else allow_upload
    if share.request_files:
        share.allow_download = False


def _get_cached_project(db: Session, project_id: str | None, project_cache: dict[str, object | None] | None):
    if not project_id:
        return None
    if project_cache is None:
        project_cache = {}
    if project_id not in project_cache:
        try:
            project_cache[project_id] = get_horizon_project(db, project_id)
        except Exception:
            project_cache[project_id] = None
    return project_cache[project_id]
