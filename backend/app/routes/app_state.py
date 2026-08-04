from __future__ import annotations

import time

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from app.db import SessionLocal
from app.models import RecentlyViewed
from app.services.auth import get_user_from_session
from app.services.file_access import check_folder_read_permission
from app.services.horizons.projects import list_visible_horizon_projects
from app.services.recently_viewed import exclude_deleted_project_recently_viewed
from app.services.search_index import filter_search_index_for_user, get_search_index

router = APIRouter(tags=['app-state'])


class RecentlyViewedItem(BaseModel):
    type: str
    id: str
    projectId: str | None = None
    title: str | None = None
    subtitle: str | None = None


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
        can_browse_files = bool(
            user.get('role') == 'admin'
            or (user.get('app_access') or {}).get('file_browser')
        )

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
