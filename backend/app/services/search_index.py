from __future__ import annotations

import os
import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import HorizonProject, HorizonTracker
from app.runtime_state import SEARCH_INDEX_MAX_FILES, SEARCH_INDEX_TTL_SECONDS, _search_index_cache, _search_index_lock
from app.services.file_access import check_folder_read_permission
from app.services.horizons_fresh import DELETED_PROJECT_STATUS
from app.services.horizons.projects import list_visible_horizon_projects
from app.services.user_access import has_app_access

settings = get_settings()
MEDIA_ROOT = settings.MEDIA_ROOT
HIDDEN_FOLDERS = settings.hidden_storage_folders


def build_search_index() -> dict:
    projects = []
    trackers = []
    files = []

    db = SessionLocal()
    try:
        horizon_projects = (
            db.query(HorizonProject)
            .filter(HorizonProject.status != DELETED_PROJECT_STATUS)
            .order_by(HorizonProject.updated_at.desc(), HorizonProject.created_at.desc())
            .all()
        )
        project_title_by_id = {}
        for project in horizon_projects:
            project_title = project.title or 'Untitled'
            project_title_by_id[project.id] = project_title
            projects.append((project.id, project_title, project.status, project_title.lower()))

        for tracker in (
            db.query(HorizonTracker)
            .order_by(HorizonTracker.created_at.asc())
            .all()
        ):
            project_title = project_title_by_id.get(tracker.project_id)
            if not project_title:
                continue
            tracker_name = tracker.name or tracker.slug or tracker.id
            trackers.append((tracker.project_id, project_title, tracker_name, tracker_name.lower()))
    except Exception:
        print('Error indexing project data for search')
    finally:
        db.close()

    indexed_files = 0
    if MEDIA_ROOT.exists():
        try:
            for root, dirs, names in os.walk(MEDIA_ROOT):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in HIDDEN_FOLDERS]
                for filename in names:
                    if filename.startswith('.'):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, filename), MEDIA_ROOT)
                    folder = os.path.dirname(rel_path) or '/'
                    files.append((filename.lower(), filename, rel_path, folder))
                    indexed_files += 1
                    if indexed_files >= SEARCH_INDEX_MAX_FILES:
                        break
                if indexed_files >= SEARCH_INDEX_MAX_FILES:
                    break
        except Exception:
            print('Error indexing files for search')

    return {'built_at': time.time(), 'projects': projects, 'trackers': trackers, 'files': files}


def get_search_index() -> dict:
    now = time.time()
    with _search_index_lock:
        if _search_index_cache['built_at'] and now - _search_index_cache['built_at'] < SEARCH_INDEX_TTL_SECONDS:
            return _search_index_cache
        rebuilt = build_search_index()
        _search_index_cache.update(rebuilt)
        return _search_index_cache


def filter_search_index_for_user(index: dict, user: dict, db: Session) -> dict:
    visible_project_ids = {
        project.id
        for project in list_visible_horizon_projects(db, user)
    }
    can_search_files = has_app_access(user, 'file_browser')
    return {
        'built_at': index.get('built_at', 0.0),
        'projects': [
            item for item in index.get('projects', [])
            if item[0] in visible_project_ids
        ],
        'trackers': [
            item for item in index.get('trackers', [])
            if item[0] in visible_project_ids
        ],
        'files': [
            item for item in index.get('files', [])
            if can_search_files and check_folder_read_permission(user, item[2])
        ],
    }


def invalidate_search_index() -> None:
    with _search_index_lock:
        _search_index_cache.update({
            'built_at': 0.0,
            'projects': [],
            'trackers': [],
            'files': [],
        })
