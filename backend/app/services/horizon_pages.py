from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import HorizonPage, HorizonShotVersion, HorizonTracker, MediaAsset
from app.services.external_urls import normalize_external_http_url
from app.services.naming import slugify
from app.services.projects import get_project_dir

PAGE_BLOCK_TYPES = {'text', 'tracker_list', 'resource_list', 'upload_inbox'}


def _normalize_runtime_path(path: str | None, *, allow_empty: bool = False) -> str:
    value = str(path or '').strip().strip('/')
    if not value:
        if allow_empty:
            return ''
        raise HTTPException(status_code=400, detail='Path is required')
    parts = []
    for part in value.split('/'):
        part = part.strip()
        if not part or part == '.':
            continue
        if part == '..':
            raise HTTPException(status_code=400, detail='Parent traversal is not allowed')
        if part.startswith('.'):
            raise HTTPException(status_code=400, detail='Hidden paths are not allowed')
        parts.append(part)
    normalized = '/'.join(parts)
    if not normalized and not allow_empty:
        raise HTTPException(status_code=400, detail='Path is required')
    return normalized


def _make_block_id() -> str:
    return f'block-{str(uuid.uuid4())[:8]}'


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clean_string(value: Any, *, default: str = '') -> str:
    text = str(value if value is not None else default).strip()
    return text


def _normalize_resource(resource: dict) -> dict | None:
    if not isinstance(resource, dict):
        return None
    kind = _clean_string(resource.get('kind') or resource.get('type') or 'file').lower()
    if kind not in {'file', 'folder', 'url'}:
        kind = 'url' if resource.get('url') else 'file'
    label = _clean_string(resource.get('label') or resource.get('name'))
    if kind == 'url':
        url = normalize_external_http_url(resource.get('url') or resource.get('path'))
        if not url:
            return None
        return {
            'id': _clean_string(resource.get('id'), default=f'resource-{str(uuid.uuid4())[:8]}'),
            'kind': 'url',
            'label': label or url,
            'url': url,
        }
    path = _normalize_runtime_path(resource.get('path') or resource.get('file_path'), allow_empty=False)
    return {
        'id': _clean_string(resource.get('id'), default=f'resource-{str(uuid.uuid4())[:8]}'),
        'kind': kind,
        'label': label or Path(path).name,
        'path': path,
    }


def _normalize_tracker_refs(block: dict) -> list[str]:
    raw = block.get('tracker_ids')
    if raw is None:
        raw = block.get('trackers')
    if raw is None:
        raw = block.get('trackerRefs')
    refs = []
    for item in _as_list(raw):
        if isinstance(item, dict):
            value = item.get('id') or item.get('name') or item.get('slug')
        else:
            value = item
        ref = _clean_string(value)
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def normalize_page_blocks(blocks: list[dict] | None, *, page_slug: str | None = None) -> list[dict]:
    normalized = []
    for raw_block in _as_list(blocks):
        if not isinstance(raw_block, dict):
            continue
        block_type = _clean_string(raw_block.get('type')).lower()
        if block_type not in PAGE_BLOCK_TYPES:
            continue
        block = {
            'id': _clean_string(raw_block.get('id'), default=_make_block_id()),
            'type': block_type,
            'title': _clean_string(raw_block.get('title')),
            'hidden': bool(raw_block.get('hidden', False)),
        }
        if block_type == 'text':
            block['body'] = _clean_string(raw_block.get('body') or raw_block.get('text'))
        elif block_type == 'tracker_list':
            block['tracker_ids'] = _normalize_tracker_refs(raw_block)
        elif block_type == 'resource_list':
            resources = []
            for resource in _as_list(raw_block.get('resources') or raw_block.get('items')):
                try:
                    normalized_resource = _normalize_resource(resource)
                except HTTPException:
                    continue
                if normalized_resource:
                    resources.append(normalized_resource)
            block['resources'] = resources
        elif block_type == 'upload_inbox':
            target_path = raw_block.get('target_path') or raw_block.get('path')
            if not target_path:
                target_path = f'client-uploads/{page_slug or "page"}'
            block['target_path'] = _normalize_runtime_path(target_path, allow_empty=False)
            block['description'] = _clean_string(raw_block.get('description'))
            block['enabled'] = bool(raw_block.get('enabled', True))
        normalized.append(block)
    return normalized


def default_page_blocks(page_slug: str) -> list[dict]:
    return normalize_page_blocks([
        {'type': 'text', 'title': 'Overview', 'body': ''},
        {'type': 'tracker_list', 'title': 'Trackers', 'tracker_ids': []},
        {'type': 'resource_list', 'title': 'Resources', 'resources': []},
        {'type': 'upload_inbox', 'title': 'Client Uploads', 'target_path': f'client-uploads/{page_slug}', 'enabled': True},
    ], page_slug=page_slug)


def _load_blocks(page: HorizonPage) -> list[dict]:
    try:
        loaded = json.loads(page.blocks_json or '[]')
    except Exception:
        loaded = []
    return normalize_page_blocks(loaded, page_slug=page.slug)


def _dump_blocks(blocks: list[dict]) -> str:
    return json.dumps(blocks or [], separators=(',', ':'))


def _unique_page_slug(db: Session, project_id: str, title: str, existing_page_id: str | None = None) -> str:
    base = slugify(title, f'page-{str(uuid.uuid4())[:8]}')
    slug = base
    counter = 2
    while True:
        query = db.query(HorizonPage).filter(HorizonPage.project_id == project_id).filter(HorizonPage.slug == slug)
        if existing_page_id:
            query = query.filter(HorizonPage.id != existing_page_id)
        if query.first() is None:
            return slug
        slug = f'{base}-{counter}'
        counter += 1


def list_horizon_pages(db: Session, project_id: str) -> list[HorizonPage]:
    return (
        db.query(HorizonPage)
        .filter(HorizonPage.project_id == project_id)
        .order_by(HorizonPage.created_at.asc())
        .all()
    )


def get_horizon_page_by_ref(db: Session, project_id: str, page_ref: str) -> HorizonPage:
    value = _clean_string(page_ref)
    page = (
        db.query(HorizonPage)
        .filter(HorizonPage.project_id == project_id)
        .filter((HorizonPage.id == value) | (HorizonPage.slug == value))
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail='Page not found')
    return page


def create_horizon_page(
    db: Session,
    project_id: str,
    *,
    title: str,
    description: str | None = None,
    cover_path: str | None = None,
    blocks: list[dict] | None = None,
    created_by: str | None = None,
) -> HorizonPage:
    normalized_title = _clean_string(title)
    if not normalized_title:
        raise HTTPException(status_code=400, detail='Page title is required')
    now = time.time()
    slug = _unique_page_slug(db, project_id, normalized_title)
    normalized_blocks = normalize_page_blocks(blocks, page_slug=slug) if blocks is not None else default_page_blocks(slug)
    page = HorizonPage(
        id=str(uuid.uuid4()),
        project_id=project_id,
        slug=slug,
        title=normalized_title,
        description=description,
        cover_path=_normalize_runtime_path(cover_path, allow_empty=True) if cover_path else None,
        blocks_json=_dump_blocks(normalized_blocks),
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def update_horizon_page(
    db: Session,
    project_id: str,
    page_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    cover_path: str | None = None,
    blocks: list[dict] | None = None,
    fields_set: set[str] | None = None,
) -> HorizonPage:
    page = get_horizon_page_by_ref(db, project_id, page_id)
    fields = set(fields_set or set())
    if 'title' in fields:
        normalized_title = _clean_string(title)
        if not normalized_title:
            raise HTTPException(status_code=400, detail='Page title is required')
        page.title = normalized_title
        page.slug = _unique_page_slug(db, project_id, normalized_title, existing_page_id=page.id)
    if 'description' in fields:
        page.description = description
    if 'cover_path' in fields:
        page.cover_path = _normalize_runtime_path(cover_path, allow_empty=True) if cover_path else None
    if 'blocks' in fields:
        page.blocks_json = _dump_blocks(normalize_page_blocks(blocks, page_slug=page.slug))
    page.updated_at = time.time()
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def delete_horizon_page(db: Session, project_id: str, page_id: str) -> None:
    page = get_horizon_page_by_ref(db, project_id, page_id)
    db.delete(page)
    db.commit()


def build_page_content_item(page: HorizonPage) -> dict:
    blocks = _load_blocks(page)
    return {
        'id': page.id,
        'name': page.title,
        'title': page.title,
        'description': page.description or '',
        'path': page.slug,
        'slug': page.slug,
        'type': 'page',
        'source': 'horizons_db',
        'block_count': len([block for block in blocks if not block.get('hidden')]),
        'updated_at': page.updated_at,
        'created_at': page.created_at,
    }


def _resolve_page_tracker(db: Session, project_id: str, ref: str) -> HorizonTracker | None:
    ref = _clean_string(ref)
    if not ref:
        return None
    return (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == project_id)
        .filter((HorizonTracker.id == ref) | (HorizonTracker.slug == ref) | (HorizonTracker.name == ref))
        .first()
    )


def get_page_tracker_refs(page: HorizonPage) -> list[str]:
    refs = []
    for block in _load_blocks(page):
        if block.get('type') != 'tracker_list' or block.get('hidden'):
            continue
        for ref in block.get('tracker_ids') or []:
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def get_page_tracker_ids(db: Session, page: HorizonPage) -> set[str]:
    ids = set()
    for ref in get_page_tracker_refs(page):
        tracker = _resolve_page_tracker(db, page.project_id, ref)
        if tracker:
            ids.add(tracker.id)
    return ids


def page_allows_tracker(db: Session, page: HorizonPage, tracker: HorizonTracker | str) -> bool:
    if isinstance(tracker, HorizonTracker):
        tracker_id = tracker.id
    else:
        resolved = _resolve_page_tracker(db, page.project_id, tracker)
        tracker_id = resolved.id if resolved else None
    return bool(tracker_id and tracker_id in get_page_tracker_ids(db, page))


def _path_within(root_path: str | None, candidate_path: str | None) -> bool:
    root = _clean_string(root_path).strip('/')
    candidate = _clean_string(candidate_path).strip('/')
    if not root:
        return False
    return candidate == root or candidate.startswith(f'{root}/')


def page_allows_path(page: HorizonPage, path: str | None) -> bool:
    normalized_path = _clean_string(path).strip('/')
    if not normalized_path:
        return False
    for block in _load_blocks(page):
        if block.get('type') != 'resource_list' or block.get('hidden'):
            continue
        for resource in block.get('resources') or []:
            kind = resource.get('kind')
            resource_path = _clean_string(resource.get('path')).strip('/')
            if kind == 'file' and normalized_path == resource_path:
                return True
            if kind == 'folder' and _path_within(resource_path, normalized_path):
                return True
    return False


def page_allows_zip_path(page: HorizonPage, path: str | None) -> bool:
    return bool(page_zip_resource_paths(page, path))


def page_zip_resource_paths(page: HorizonPage, path: str | None) -> list[str]:
    normalized_path = _clean_string(path).strip('/')
    if not normalized_path:
        return []
    for block in _load_blocks(page):
        if block.get('type') != 'resource_list' or block.get('hidden'):
            continue
        for resource in block.get('resources') or []:
            kind = resource.get('kind')
            resource_path = _clean_string(resource.get('path')).strip('/')
            if not resource_path:
                continue
            if kind == 'file' and normalized_path == resource_path:
                return [resource_path]
            if kind == 'folder' and _path_within(resource_path, normalized_path):
                return [normalized_path]

    prefix = f'{normalized_path}/'
    paths: list[str] = []
    for block in _load_blocks(page):
        if block.get('type') != 'resource_list' or block.get('hidden'):
            continue
        for resource in block.get('resources') or []:
            resource_path = _clean_string(resource.get('path')).strip('/')
            if resource_path.startswith(prefix) and resource_path not in paths:
                paths.append(resource_path)
    return paths


def page_allows_media_asset(db: Session, page: HorizonPage, asset: MediaAsset | None, version: HorizonShotVersion | None = None) -> bool:
    if version is not None and version.tracker_id in get_page_tracker_ids(db, page):
        from app.services.horizons.version_publication import version_is_published

        return version_is_published(version)
    if asset is not None and page_allows_path(page, asset.file_path):
        return True
    if asset is not None and asset.storage_scope == 'media_root':
        from app.services.project_links import linked_virtual_paths_for_source
        from app.services.projects import load_project_links

        virtual_paths = linked_virtual_paths_for_source(load_project_links(page.project_id).get('links', []), asset.file_path)
        if any(page_allows_path(page, path) for path in virtual_paths):
            return True
    return False


def get_page_upload_targets(page: HorizonPage) -> list[str]:
    targets = []
    for block in _load_blocks(page):
        if block.get('type') != 'upload_inbox' or block.get('hidden') or not block.get('enabled', True):
            continue
        target = _clean_string(block.get('target_path')).strip('/')
        if target and target not in targets:
            targets.append(target)
    return targets


def page_allows_upload_target(page: HorizonPage, target_path: str | None) -> bool:
    normalized = _clean_string(target_path).strip('/')
    for target in get_page_upload_targets(page):
        if normalized == target or _path_within(target, normalized):
            return True
    return False


def _serialize_tracker_ref(db: Session, page: HorizonPage, tracker_ref: str, *, public: bool = False) -> dict | None:
    tracker = _resolve_page_tracker(db, page.project_id, tracker_ref)
    if not tracker:
        return None
    try:
        from app.services.horizons_fresh import compute_horizon_tracker_stats

        stats = compute_horizon_tracker_stats(db, tracker, published_only=public)
    except Exception:
        stats = {}
    updated_at = tracker.updated_at
    if public:
        from app.services.horizons.version_publication import latest_published_at_for_tracker

        updated_at = latest_published_at_for_tracker(db, tracker.project_id, tracker.id) or tracker.created_at
    return {
        'id': tracker.id,
        'slug': tracker.slug,
        'name': tracker.name,
        'path': tracker.id,
        'type': 'tracker',
        'created_at': tracker.created_at,
        'updated_at': updated_at,
        'shot_count': stats.get('totalShots') or 0,
        'total_duration': stats.get('totalDuration') or 0,
        'total_frames': stats.get('totalFrames') or 0,
        'total_versions': stats.get('totalVersions') or 0,
        'done_shots': stats.get('doneShots') or 0,
        'average_shot_duration': stats.get('averageShotDuration') or 0,
        'status_breakdown': stats.get('statusBreakdown') or [],
    }


def _serialize_resource(
    db: Session,
    project_id: str,
    resource: dict,
    *,
    held_asset_ids: set[str] | None = None,
    held_paths: set[Path] | None = None,
) -> dict | None:
    item = dict(resource)
    if item.get('kind') in {'file', 'folder'} and item.get('path'):
        path = _clean_string(item.get('path')).strip('/')
        item['path'] = path
        item.setdefault('label', Path(path).name)
        if item.get('kind') == 'file':
            try:
                from app.services.horizons_fresh import get_horizon_media_asset_by_path
                from app.services.media_resolution import resolve_project_link_target
                from app.services.share_access import build_project_file_info_payload

                asset = get_horizon_media_asset_by_path(db, project_id, path)
                if asset is not None and str(asset.id) in (held_asset_ids or set()):
                    return None
                full_path, _cache_key, storage_scope = resolve_project_link_target(project_id, path)
                if not full_path:
                    from app.services.projects import resolve_horizon_project_root

                    project_path = resolve_horizon_project_root(db, project_id) / path
                    full_path = project_path if project_path.exists() else None
                if (
                    full_path is not None
                    and full_path.resolve(strict=False) in (held_paths or set())
                ):
                    return None
                file_info = build_project_file_info_payload(
                    project_id,
                    path,
                    full_path,
                    db=db,
                    storage_scope=storage_scope,
                    asset=asset,
                    exists=bool(full_path and full_path.exists()),
                )
                item.update(file_info)
                item['kind'] = 'file'
            except Exception:
                item.setdefault('name', item.get('label') or Path(path).name)
                item.setdefault('type', 'file')
    return item


def serialize_horizon_page(db: Session, page: HorizonPage, *, include_resolved: bool = True, public: bool = False) -> dict:
    held_asset_ids: set[str] = set()
    held_paths: set[Path] = set()
    if public:
        from app.services.horizons.version_publication import (
            held_media_asset_ids_for_project,
            held_media_paths_for_project,
        )

        held_asset_ids = held_media_asset_ids_for_project(db, page.project_id)
        held_paths = held_media_paths_for_project(db, page.project_id)
    cover_path = page.cover_path
    if public and cover_path:
        from app.services.horizons_fresh import get_horizon_media_asset_by_path
        from app.services.media_resolution import resolve_project_link_target

        cover_asset = get_horizon_media_asset_by_path(db, page.project_id, cover_path)
        cover_full_path, _cache_key, _scope = resolve_project_link_target(
            page.project_id,
            cover_path,
        )
        if (
            (cover_asset is not None and str(cover_asset.id) in held_asset_ids)
            or (
                cover_full_path is not None
                and cover_full_path.resolve(strict=False) in held_paths
            )
        ):
            cover_path = None
    blocks = []
    for block in _load_blocks(page):
        if public and block.get('hidden'):
            continue
        next_block = dict(block)
        if include_resolved and block.get('type') == 'tracker_list':
            next_block['trackers'] = [
                tracker
                for tracker in (
                    _serialize_tracker_ref(db, page, ref, public=public)
                    for ref in block.get('tracker_ids') or []
                )
                if tracker is not None
            ]
        elif include_resolved and block.get('type') == 'resource_list':
            next_block['resources'] = [
                serialized
                for serialized in (
                    _serialize_resource(
                        db,
                        page.project_id,
                        resource,
                        held_asset_ids=held_asset_ids,
                        held_paths=held_paths,
                    )
                    for resource in (block.get('resources') or [])
                )
                if serialized is not None
            ]
        blocks.append(next_block)

    return {
        'id': page.id,
        'project_id': page.project_id,
        'slug': page.slug,
        'title': page.title,
        'description': page.description or '',
        'cover_path': cover_path,
        'blocks': blocks,
        'created_by': page.created_by,
        'created_at': page.created_at,
        'updated_at': page.updated_at,
        'type': 'page',
    }
