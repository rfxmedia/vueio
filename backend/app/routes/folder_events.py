from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import SessionLocal
from app.limiter import client_rate_limit_key, enforce_rate_limit
from app.services.auth import get_user_from_session
from app.services.file_access import _permission_path_parts, check_folder_navigation_permission, check_folder_read_permission
from app.services.folder_events import FolderBinding, folder_events
from app.services.horizon_pages import get_horizon_page_by_ref, page_allows_path
from app.services.horizons.projects import get_horizon_project, require_horizon_project_access
from app.services.horizons.team import get_horizon_user_workspace_path
from app.services.media import get_safe_path
from app.services.project_access import verify_path_in_project
from app.services.project_content_gateway import HorizonsProjectAuthPolicy
from app.services.project_links import find_link_target, linked_virtual_root, resolve_link_source_path
from app.services.projects import load_project_links, project_links_path, resolve_project_root
from app.services.share_access import normalize_virtual_path, require_path_within_shared_root, validate_share
from app.services.user_access import has_app_access, is_restricted_project_member


router = APIRouter(tags=['files'])
settings = get_settings()
_HIDDEN = frozenset(settings.hidden_storage_folders)
_PROJECT_HIDDEN = _HIDDEN | {'project.json'}


def _binding(
    target: Path,
    root: Path,
    virtual_path: str,
    *,
    names: frozenset[str] | None = None,
    excluded_names: frozenset[str] = _HIDDEN,
) -> FolderBinding:
    verify_path_in_project(target, root)
    target = target.resolve()
    root = root.resolve()
    # Virtual folders and a just-deleted folder can have no physical directory.
    # Observe only their nearest existing parent until the next authorized bind.
    while not target.is_dir() and target != root:
        names = frozenset({target.name})
        target = target.parent
    if not target.is_dir():
        raise HTTPException(status_code=404, detail='Folder not found')
    return FolderBinding(target, virtual_path, names, excluded_names)


def _project_bindings(db, project, paths: tuple[str, ...], user=None, access_role=None, share=None) -> tuple[FolderBinding, ...]:
    root = resolve_project_root(project)
    links = load_project_links(project.id).get('links', []) or []
    policy = HorizonsProjectAuthPolicy(db, project.id, user, access_role) if user else None
    shared_page = get_horizon_page_by_ref(db, project.id, share.page_id or '') if share and share.share_type == 'page' else None
    bindings = []
    for requested_path in paths:
        path = requested_path
        if share and share.share_type == 'project-folder':
            path = require_path_within_shared_root(share.path or '', path or share.path or '')
        if shared_page and (not path or not page_allows_path(shared_page, path)):
            raise HTTPException(status_code=403, detail='This page does not grant access to the requested folder')
        if policy:
            policy.assert_can_list(path)
        names = None
        if user and is_restricted_project_member(user) and not path:
            names = frozenset({get_horizon_user_workspace_path(user)})
        match = find_link_target(links, path)
        if match and (match[0].get('type') or 'file') == 'folder':
            target = resolve_link_source_path(match[0], project_root=root, suffix=match[1])
            if target is None:
                raise HTTPException(status_code=404, detail='Linked folder not found')
            boundary = root if match[0].get('storage_scope') == 'project' else settings.MEDIA_ROOT
        else:
            target = root / path
            boundary = root
        bindings.append(_binding(target, boundary, requested_path, names=names, excluded_names=_PROJECT_HIDDEN))
        # A direct linked file/folder can change without touching its virtual
        # parent. Watch its source entry, not the source directory's siblings.
        for link in links:
            virtual_root = linked_virtual_root(link)
            if virtual_root.rpartition('/')[0] != path:
                continue
            if names is not None and Path(virtual_root).name not in names:
                continue
            source = resolve_link_source_path(link, project_root=root)
            if source is None:
                continue
            source_root = root if link.get('storage_scope') == 'project' else settings.MEDIA_ROOT
            bindings.append(_binding(source.parent, source_root, requested_path, names=frozenset({source.name})))
        # Link definitions live in private application storage even when the
        # actual project files live on a configured external drive.
        links_file = project_links_path(project.id)
        bindings.append(_binding(links_file.parent, settings.projects_dir, requested_path, names=frozenset({links_file.name})))
    return tuple(dict.fromkeys(bindings))


def _resolve_bindings(paths: tuple[str, ...], project_id: str | None, share_id: str | None, session: str | None) -> tuple[str, tuple[FolderBinding, ...]]:
    with SessionLocal() as db:
        if share_id:
            share = validate_share(share_id, None, db, ['folder', 'project-folder', 'project', 'page'], track_access=False)
            if project_id and project_id != share.project_id:
                raise HTTPException(status_code=403, detail='Project does not match this share')
            if share.project_id:
                project = get_horizon_project(db, share.project_id)
                return f'share:{share.id}', _project_bindings(db, project, paths, share=share)
            if share.share_type != 'folder' or not share.is_folder:
                raise HTTPException(status_code=400, detail='Share is not a folder')
            bindings = []
            for requested_path in paths:
                path = require_path_within_shared_root(share.path or '', requested_path or share.path or '')
                bindings.append(_binding(get_safe_path(path), settings.MEDIA_ROOT, requested_path))
            return f'share:{share.id}', tuple(bindings)

        user = get_user_from_session(session, allow_agent_fallback=False)
        if not user:
            raise HTTPException(status_code=401, detail='Not authenticated')
        if project_id:
            project, access_role = require_horizon_project_access(db, project_id, user, auth_mode='session', required_role='viewer')
            return f'user:{user["id"]}', _project_bindings(db, project, paths, user, access_role)
        if not has_app_access(user, 'file_browser'):
            raise HTTPException(status_code=403, detail='File Browser access required')
        bindings = []
        for path in paths:
            if path and not check_folder_navigation_permission(user, path):
                raise HTTPException(status_code=403, detail='Access denied to this path')
            names = None
            if not check_folder_read_permission(user, path):
                prefix = _permission_path_parts(path) or ()
                names = frozenset(
                    parts[len(prefix)]
                    for value in (user.get('folder_permissions') or [])
                    if (parts := _permission_path_parts(value)) is not None
                    if len(parts) > len(prefix) and parts[:len(prefix)] == prefix
                )
            bindings.append(_binding(get_safe_path(path), settings.MEDIA_ROOT, path, names=names))
        return f'user:{user["id"]}', tuple(bindings)


def _event(name: str, paths: list[str] | tuple[str, ...]) -> str:
    return f'event: {name}\ndata: {json.dumps({"paths": paths}, separators=(",", ":"))}\n\n'


@router.get('/api/folder-events')
async def folder_event_stream(
    request: Request,
    path: list[str] = Query(default=[''], max_length=64),
    project_id: str | None = Query(default=None, max_length=100),
    share_id: str | None = Query(default=None, max_length=100),
    vueio_session: str | None = Cookie(None),
):
    if not path or any(len(item) > 2048 for item in path) or sum(map(len, path)) > 16000:
        raise HTTPException(status_code=400, detail='Too many folders or folder paths are too long')
    paths = tuple(dict.fromkeys(normalize_virtual_path(item, allow_empty=True) for item in path))
    enforce_rate_limit(request, '120/minute', scope='folder-events')
    owner, bindings = await run_in_threadpool(_resolve_bindings, paths, project_id, share_id, vueio_session)
    if share_id:
        owner = f'{owner}:{client_rate_limit_key(request)}'
    try:
        subscription = folder_events.subscribe(owner, bindings)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def stream():
        checked_at = time.monotonic()
        try:
            await folder_events.ready(subscription)
            yield _event('ready', paths)
            while subscription in folder_events.subscriptions:
                try:
                    await asyncio.wait_for(subscription.changed.wait(), timeout=15)
                except TimeoutError:
                    pass
                if subscription not in folder_events.subscriptions:
                    return
                changed = subscription.take_changes()
                if changed or time.monotonic() - checked_at >= 30:
                    try:
                        _owner, current = await run_in_threadpool(_resolve_bindings, paths, project_id, share_id, vueio_session)
                        if folder_events.update(subscription, current):
                            changed = list(paths)
                        checked_at = time.monotonic()
                    except (HTTPException, OSError, RuntimeError):
                        # A stream cannot change its HTTP status after headers.
                        # Tell the browser to close it; normal list requests keep
                        # enforcing access, including revoked shares and sessions.
                        yield _event('denied', ())
                        return
                if changed:
                    yield _event('change', changed)
                else:
                    yield ': keepalive\n\n'
        finally:
            folder_events.unsubscribe(subscription)

    return StreamingResponse(stream(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-store',
        'X-Accel-Buffering': 'no',
        'X-Content-Type-Options': 'nosniff',
    })
