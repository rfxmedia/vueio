from __future__ import annotations

import time

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import (
    HorizonProject,
    HorizonShot,
    HorizonShotAssignee,
    HorizonShotVersion,
    HorizonTracker,
    RecentlyViewed,
)
from app.services.auth import get_request_user, get_user_from_session
from app.services.file_access import check_folder_read_permission
from app.services.horizons.projects import list_visible_horizon_projects
from app.services.recently_viewed import exclude_deleted_project_recently_viewed
from app.services.search_index import filter_search_index_for_user, get_search_index
from app.services.user_access import has_app_access

router = APIRouter(tags=['app-state'])


class RecentlyViewedItem(BaseModel):
    type: str
    id: str
    projectId: str | None = None
    title: str | None = None
    subtitle: str | None = None


@router.get('/api/home/assigned-edits')
def get_home_assigned_edits(
    vueio_session: str | None = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    user_id = str(user.get('id') or user.get('username') or '').strip()
    visible_projects = list_visible_horizon_projects(db, user, auth_mode=auth_mode)
    visible_project_ids = [project.id for project in visible_projects]
    if not user_id or not visible_project_ids:
        return {'total': 0, 'projects': []}

    rows = (
        db.query(HorizonShot, HorizonTracker, HorizonProject)
        .join(HorizonTracker, HorizonTracker.id == HorizonShot.tracker_id)
        .join(HorizonProject, HorizonProject.id == HorizonShot.project_id)
        .outerjoin(
            HorizonShotAssignee,
            and_(
                HorizonShotAssignee.shot_id == HorizonShot.id,
                HorizonShotAssignee.user_id == user_id,
            ),
        )
        .filter(HorizonShot.project_id.in_(visible_project_ids))
        .filter(HorizonProject.status.notin_(('done', 'completed')))
        .filter(HorizonShot.status.in_(('edits_requested', 'in_progress')))
        .filter(HorizonShot.archived_at.is_(None))
        .filter(or_(
            HorizonShotAssignee.user_id == user_id,
            HorizonShot.assignee_user_id == user_id,
        ))
        .order_by(
            HorizonProject.title.asc(),
            HorizonShot.status.asc(),
            HorizonShot.updated_at.desc(),
            HorizonTracker.name.asc(),
            HorizonShot.shot_code.asc(),
        )
        .all()
    )

    shot_ids = [shot.id for shot, _tracker, _project in rows]
    latest_version_ids: dict[str, str] = {}
    if shot_ids:
        versions = (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.shot_id.in_(shot_ids))
            .order_by(
                HorizonShotVersion.updated_at.desc(),
                HorizonShotVersion.created_at.desc(),
                HorizonShotVersion.id.asc(),
            )
            .all()
        )
        for version in versions:
            latest_version_ids.setdefault(version.shot_id, version.id)

    grouped: dict[str, dict] = {}
    for shot, tracker, project in rows:
        project_group = grouped.setdefault(project.id, {
            'id': project.id,
            'title': project.title,
            'status': project.status,
            'due_date': project.due_date,
            'thumbnail_path': project.thumbnail_path,
            'updated_at': 0,
            'shots': [],
        })
        project_group['updated_at'] = max(project_group['updated_at'], shot.updated_at or 0)
        project_group['shots'].append({
            'id': shot.id,
            'shot_id': shot.shot_code,
            'description': shot.description,
            'category': shot.category,
            'status': shot.status,
            'tracker_id': tracker.id,
            'tracker_name': tracker.name,
            'latest_version_label': shot.latest_version_label,
            'latest_version_id': latest_version_ids.get(shot.id),
            'updated_at': shot.updated_at,
        })

    projects = sorted(grouped.values(), key=lambda project: (
        -float(project['updated_at'] or 0),
        str(project['title']).casefold(),
    ))
    return {'total': len(rows), 'projects': projects}


@router.get('/api/recently-viewed')
def get_recently_viewed(limit: int = 10, vueio_session: str | None = Cookie(None)):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    limit = min(limit, 50)
    db = SessionLocal()
    try:
        query = db.query(RecentlyViewed).filter(RecentlyViewed.user_id == user['username'])
        items = exclude_deleted_project_recently_viewed(query, db).order_by(RecentlyViewed.viewed_at.desc()).all()
        visible_project_ids = {
            project.id
            for project in list_visible_horizon_projects(db, user)
        }
        can_browse_files = has_app_access(user, 'file_browser')

        def can_view_recent(item: RecentlyViewed) -> bool:
            project_id = item.project_id or (
                item.item_id
                if item.item_type in {'project', 'horizon_project'}
                else None
            )
            if project_id:
                return project_id in visible_project_ids
            if item.item_type in {'file', 'folder', 'nas_file', 'nas_folder'}:
                return can_browse_files and check_folder_read_permission(user, item.item_id)
            return True

        items = [
            item
            for item in items
            if can_view_recent(item)
        ][:limit]
        result = [{
            'type': item.item_type,
            'id': item.item_id,
            'projectId': item.project_id,
            'title': item.title,
            'subtitle': item.subtitle,
            'viewedAt': item.viewed_at,
        } for item in items]
        return {'items': result}
    finally:
        db.close()


@router.post('/api/recently-viewed')
def add_recently_viewed(data: RecentlyViewedItem, vueio_session: str | None = Cookie(None)):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    db = SessionLocal()
    try:
        existing = db.query(RecentlyViewed).filter(RecentlyViewed.user_id == user['username'], RecentlyViewed.item_type == data.type, RecentlyViewed.item_id == data.id)
        if data.type == 'tracker' and data.projectId:
            existing = existing.filter(RecentlyViewed.project_id == data.projectId)
        existing.delete()

        new_item = RecentlyViewed(
            user_id=user['username'],
            item_type=data.type,
            item_id=data.id,
            project_id=data.projectId,
            title=data.title,
            subtitle=data.subtitle,
            viewed_at=time.time(),
        )
        db.add(new_item)
        all_items = db.query(RecentlyViewed).filter(RecentlyViewed.user_id == user['username']).order_by(RecentlyViewed.viewed_at.desc()).all()
        if len(all_items) > 20:
            for old_item in all_items[20:]:
                db.delete(old_item)
        db.commit()
        return {'status': 'ok'}
    finally:
        db.close()


@router.delete('/api/recently-viewed')
def clear_recently_viewed(vueio_session: str | None = Cookie(None)):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    db = SessionLocal()
    try:
        db.query(RecentlyViewed).filter(RecentlyViewed.user_id == user['username']).delete()
        db.commit()
        return {'status': 'ok'}
    finally:
        db.close()


@router.get('/api/search')
def search_everything(q: str, vueio_session: str | None = Cookie(None)):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')

    query = q.lower().strip()
    if len(query) < 2:
        return {'projects': [], 'trackers': [], 'files': []}

    db = SessionLocal()
    try:
        index = filter_search_index_for_user(get_search_index(), user, db)
    finally:
        db.close()
    results = {'projects': [], 'trackers': [], 'files': []}

    for project_id, title, status, title_lc in index['projects']:
        if query in title_lc:
            results['projects'].append({'id': project_id, 'title': title, 'status': status})
            if len(results['projects']) >= 10:
                break

    for project_id, project_title, tracker_name, tracker_name_lc in index['trackers']:
        if query in tracker_name_lc:
            results['trackers'].append({'id': f'{project_id}_{tracker_name}', 'name': tracker_name, 'projectId': project_id, 'projectTitle': project_title})
            if len(results['trackers']) >= 10:
                break

    for filename_lc, filename, rel_path, folder in index['files']:
        if query in filename_lc:
            results['files'].append({'path': rel_path, 'name': filename, 'folder': folder})
            if len(results['files']) >= 10:
                break

    return results
