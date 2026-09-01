from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MediaAsset
from app.services.file_access import check_folder_read_permission
from app.services.horizon_entity_thumbnails import list_horizon_folder_thumbnail_paths
from app.services.horizon_pages import build_page_content_item, get_horizon_page_by_ref, list_horizon_pages, page_allows_path
from app.services.horizons.media import (
    can_access_horizon_folder_path,
    can_access_horizon_media_asset_id,
    can_access_horizon_shot_version_id,
    get_horizon_media_asset_by_path,
    list_visible_horizon_folder_assets,
    list_visible_horizon_media_assets,
)
from app.services.horizons.projects import get_horizon_project
from app.services.horizons.shots import list_visible_horizon_shots
from app.services.horizons.version_publication import held_media_asset_ids_for_project, held_media_paths_for_project
from app.services.horizons.team import (
    is_horizon_user_workspace_path,
    is_horizon_workspace_root_path,
    is_restricted_horizon_artist,
)
from app.services.horizons.trackers import list_horizon_trackers
from app.services.media import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, format_size, get_safe_path, get_video_duration_quick, needs_transcode
from app.services.media_assets import attach_canonical_media_identity, get_media_asset_kind, normalize_storage_scope, register_media_asset
from app.services.media_resolution import resolve_media_asset_path, resolve_media_target, resolve_project_link_target
from app.services.project_access import resolve_authorized_legacy_project_media_target, verify_path_in_project
from app.services.project_link_content import build_linked_folder_items, collect_project_virtual_zip_entries, count_project_folder_items, links_in_virtual_folder
from app.services.project_links import build_linked_file_item, build_linked_folder_item, find_link_by_virtual_path, join_rel_path, linked_virtual_root, link_storage_scope
from app.services.project_permissions import make_project_path_smb_mutable
from app.services.projects import get_project_dir, load_project_links, project_storage_is_read_only, resolve_project_root
from app.services.share_access import _resolve_horizons_media_target_by_refs, build_project_file_info_payload, normalize_virtual_path, resolve_shared_horizons_object_target
from app.services.zip_utils import ZipDiscoveryBudget, ZipEntry, ZipFileIdentity, collect_boundary_zip_entries, new_zip_discovery_budget, unique_arcname
from app.services.user_access import is_restricted_project_member

settings = get_settings()
PDF_EXTENSIONS = {'.pdf'}
HIDDEN_SHARED_FOLDERS = settings.hidden_storage_folders
LINKED_FOLDER_UPLOAD_DISABLED_REASON = 'Uploads are disabled inside linked storage folders. Upload into a project-owned folder or use Link from storage.'

normalize_content_path = normalize_virtual_path

@dataclass(frozen=True)
class ContentRef:
    namespace: Literal['nas', 'shared_media', 'legacy_project', 'horizons_project', 'horizons_media_asset', 'horizons_shot_version', 'linked_nas', 'page_resource']
    path: str = ''; project_id: str | None = None; share_id: str | None = None
    media_asset_id: str | None = None; shot_version_id: str | None = None
    tracker_id: str | None = None; page_id: str | None = None
    storage_scope: str | None = None; source_path: str | None = None; is_folder: bool | None = None

@dataclass(frozen=True)
class ResolvedContent:
    ref: ContentRef
    full_path: Path | None; exists: bool; cache_identity: str | None; storage_scope: str | None
    media_asset_id: str | None = None; shot_version_id: str | None = None
    canonical_path: str | None = None; physical_root: Path | None = None; payload: dict | None = None

@dataclass
class ContentListResult:
    path: str
    items: list[dict]
    breadcrumbs: list[dict] = field(default_factory=list); share_root: str = ''
    folder_context: dict = field(default_factory=dict)

@dataclass
class AuthorizedZipRequest:
    refs: list[ContentRef]; budget: ZipDiscoveryBudget
    discovered_identities: set[ZipFileIdentity]; preserve_first_arcname: bool = True

class ContentAccessPolicy(Protocol):
    name: str
    def normalize_request_path(self, raw_path: str | None, *, allow_empty: bool = True) -> str: ...
    def assert_can_list(self, path: str) -> None: ...
    def assert_can_resolve(self, ref: ContentRef, *, purpose: Literal['metadata', 'stream', 'thumbnail', 'download', 'zip']) -> ContentRef: ...
    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]: ...
    def list_folder(self, path: str, *, include_counts: bool = False) -> ContentListResult: ...
    def resolve(self, ref: ContentRef, *, purpose: str) -> ResolvedContent: ...
    def collect_zip_entries(self, request: AuthorizedZipRequest) -> list[ZipEntry]: ...

def build_project_breadcrumbs(path: str) -> list[dict]:
    breadcrumbs = [{'name': 'Home', 'path': ''}]
    current = ''
    for part in (path or '').split('/'):
        if not part: continue
        current = f'{current}/{part}' if current else part
        breadcrumbs.append({'name': part, 'path': current})
    return breadcrumbs

def _folder_time_metadata(folder_path: Path) -> dict:
    stat = folder_path.stat()
    created_at = getattr(stat, 'st_birthtime', stat.st_ctime)
    return {'ctime': created_at, 'created_at': created_at, 'mtime': stat.st_mtime, 'modified_at': stat.st_mtime}

def _virtual_path_is_inside(virtual_path: str | None, parent_path: str | None) -> bool:
    normalized = (virtual_path or '').strip('/')
    parent = (parent_path or '').strip('/')
    return True if not parent else normalized == parent or normalized.startswith(f'{parent}/')

def _is_artist_user(user: dict | None) -> bool:
    return is_restricted_project_member(user)

def _horizon_asset_map_by_path(assets: list) -> dict[str, object]:
    result: dict[str, object] = {}
    ordered_assets = sorted(assets or [], key=lambda asset: ((getattr(asset, 'file_path', '') or '').strip().strip('/'), -(getattr(asset, 'updated_at', None) or getattr(asset, 'created_at', None) or 0)))
    for asset in ordered_assets:
        path = (getattr(asset, 'file_path', '') or '').strip().strip('/')
        if path and path not in result and get_media_asset_kind(getattr(asset, 'storage_scope', None)) != 'generated':
            result[path] = asset
    return result

def append_horizon_asset_virtual_items(items: list[dict], db: Session, project_id: str, assets: list, path: str, include_counts: bool = False, folder_thumbnail_paths: set[str] | None = None) -> None:
    normalized_path = normalize_virtual_path(path, allow_empty=True)
    prefix = f'{normalized_path}/' if normalized_path else ''
    existing_keys = {(item.get('type'), item.get('name')) for item in items}
    folder_counts: dict[str, int] = {}
    file_items: list[dict] = []
    for asset in assets:
        asset_scope = normalize_storage_scope(getattr(asset, 'storage_scope', None))
        if asset_scope in {'media_root', 'tracker_version', 'thumbnail', 'transcode', 'derived_artifact'}:
            continue
        asset_path = normalize_virtual_path(getattr(asset, 'file_path', ''), allow_empty=True)
        if not asset_path:
            continue
        remainder = Path(asset_path).name if normalized_path and asset_path == normalized_path else asset_path[len(prefix):] if normalized_path and asset_path.startswith(prefix) else asset_path if not normalized_path else ''
        parts = [part for part in remainder.split('/') if part]
        if not parts:
            continue
        if len(parts) > 1:
            folder_counts[parts[0]] = folder_counts.get(parts[0], 0) + 1
            continue
        name = parts[0]
        if ('file', name) in existing_keys:
            continue
        asset_path_fs, _cache_key, storage_scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
        if get_media_asset_kind(asset_scope) == 'runtime' and not bool(asset_path_fs and asset_path_fs.exists()):
            continue
        file_item = build_project_file_info_payload(project_id, asset_path, asset_path_fs, db=db, storage_scope=storage_scope, asset=asset, exists=bool(asset_path_fs and asset_path_fs.exists()))
        file_item['is_linked'] = False
        file_items.append(file_item)
        existing_keys.add(('file', name))
    for folder_name, asset_count in folder_counts.items():
        if ('folder', folder_name) in existing_keys:
            continue
        folder_path = join_rel_path(normalized_path, folder_name).strip('/')
        items.append({'name': folder_name, 'path': folder_path, 'type': 'folder', 'item_count': asset_count if include_counts else None, 'is_virtual_asset_folder': True, 'storage_scope': 'horizons_db', 'custom_thumbnail': folder_path in (folder_thumbnail_paths or set())})
        existing_keys.add(('folder', folder_name))
    items.extend(file_items)

def append_linked_project_items(db: Session, project_id: str, items: list[dict], links: list[dict], normalized_path: str, *, include_counts: bool, folder_thumbnail_paths: set[str] | None = None, allowed_virtual_root: str | None = None, probe_video_duration: bool = False) -> None:
    links_in_folder = links_in_virtual_folder(links, normalized_path)
    existing_names = {(item.get('type'), item.get('name')) for item in items}
    for link in links_in_folder:
        virtual_root = linked_virtual_root(link)
        if allowed_virtual_root and not _virtual_path_is_inside(virtual_root, allowed_virtual_root):
            continue
        source_rel_path = str(link.get('source_path') or '').strip()
        storage_scope = link_storage_scope(link)
        source_path, _cache_key, _resolved_scope = resolve_media_target(
            source_rel_path,
            project_id,
            storage_scope,
            db=db,
        )
        if source_path is None:
            continue
        link_type = link.get('type') or 'file'
        if (link_type == 'folder' and ('folder', source_path.name) in existing_names) or (link_type != 'folder' and ('file', source_path.name) in existing_names):
            continue
        if link_type == 'folder':
            if not source_path.exists() or not source_path.is_dir():
                continue
            item_count = None
            if include_counts:
                try:
                    item_count = sum(1 for child in source_path.iterdir() if not child.is_symlink() and not child.name.startswith('.'))
                except Exception:
                    item_count = 0
            folder_item = build_linked_folder_item(name=source_path.name, virtual_path=virtual_root, source_path=source_rel_path, item_count=item_count, storage_scope=storage_scope)
            folder_item.update(_folder_time_metadata(source_path))
            folder_item['custom_thumbnail'] = folder_item.get('path') in (folder_thumbnail_paths or set())
            items.append(folder_item)
            continue
        if not source_path.exists() or not source_path.is_file():
            continue
        stat = source_path.stat()
        ext = source_path.suffix.lower()
        duration = get_video_duration_quick(source_path) if probe_video_duration and ext in VIDEO_EXTENSIONS else 0
        asset = register_media_asset(db, project_id, source_rel_path, storage_scope=storage_scope)
        items.append(build_linked_file_item(name=source_path.name, virtual_path=virtual_root, source_path=source_rel_path, extension=ext.lstrip('.'), size=stat.st_size, size_formatted=format_size(stat.st_size), mtime=stat.st_mtime, ctime=getattr(stat, 'st_birthtime', stat.st_ctime), is_video=ext in VIDEO_EXTENSIONS, is_image=ext in IMAGE_EXTENSIONS, is_pdf=ext in PDF_EXTENSIONS, duration=duration, duration_formatted=f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else '', needs_transcode=needs_transcode(source_path) if ext in VIDEO_EXTENSIONS else False, media_asset_id=asset.id if asset else None, storage_scope=storage_scope))

def _append_workspace_tracker_shortcuts(db: Session, project_id: str, items: list[dict], *, user: dict | None, access_role: str | None) -> None:
    existing_tracker_names = {item.get('name') for item in items if item.get('type') == 'tracker'}
    for tracker in list_horizon_trackers(db, project_id):
        if tracker.name in existing_tracker_names:
            continue
        shot_count = len(list_visible_horizon_shots(db, project_id, tracker_id=tracker.id, user=user, access_role=access_role))
        if shot_count > 0:
            items.append({'id': tracker.id, 'slug': tracker.slug, 'name': tracker.name, 'path': tracker.id, 'type': 'tracker', 'shot_count': shot_count, 'last_activity_at': tracker.last_activity_at, 'source': 'horizons_db', 'is_shortcut': True})
            existing_tracker_names.add(tracker.name)

class HorizonsProjectAuthPolicy:
    name = 'horizons_project_auth'

    def __init__(self, db: Session, project_id: str, user: dict | None, access_role: str | None):
        self.db = db
        self.project_id = project_id
        self.user = user
        self.access_role = access_role
        self.project = get_horizon_project(db, project_id)
        self.project_dir = resolve_project_root(self.project)

    def normalize_request_path(self, raw_path: str | None, *, allow_empty: bool = True) -> str:
        return normalize_virtual_path(raw_path, allow_empty=allow_empty)

    def assert_can_list(self, path: str) -> None:
        if (
            _is_artist_user(self.user)
            and path
            and not can_access_horizon_folder_path(
                self.db,
                self.project_id,
                path,
                user=self.user,
                access_role=self.access_role,
            )
        ):
            raise HTTPException(status_code=404, detail='Folder not found')

    def assert_can_resolve(self, ref: ContentRef, *, purpose: Literal['metadata', 'stream', 'thumbnail', 'download', 'zip']) -> ContentRef:
        return ref

    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]:
        refs = [ContentRef(namespace='horizons_project', project_id=self.project_id, path=self.normalize_request_path(path, allow_empty=False)) for path in raw_paths]
        if is_restricted_horizon_artist(self.user, self.access_role):
            for ref in refs:
                self.assert_can_list(ref.path)
        return refs

    def list_folder(self, path: str, *, include_counts: bool = False) -> ContentListResult:
        normalized_path = self.normalize_request_path(path)
        project_dir = self.project_dir
        links = load_project_links(self.project_id).get('links', []) or []
        folder_visible_assets = list_visible_horizon_folder_assets(self.db, self.project_id, normalized_path, user=self.user, access_role=self.access_role)
        folder_asset_by_path = _horizon_asset_map_by_path(folder_visible_assets)
        folder_thumbnail_paths = list_horizon_folder_thumbnail_paths(self.project_id)
        linked_match = find_link_by_virtual_path(links, normalized_path)
        if _is_artist_user(self.user) and linked_match and (linked_match.get('type') or 'file') == 'folder':
            if not can_access_horizon_folder_path(
                self.db,
                self.project_id,
                normalized_path,
                user=self.user,
                access_role=self.access_role,
            ):
                raise HTTPException(status_code=403, detail='Access denied to linked horizons folder')
        linked_folder_items = build_linked_folder_items(links, normalized_path, include_counts=include_counts, folder_thumbnail_paths=folder_thumbnail_paths, db=self.db, project_id=self.project_id)
        if linked_folder_items is not None:
            return ContentListResult(normalized_path, linked_folder_items, build_project_breadcrumbs(normalized_path), folder_context={'mode': 'linked', 'is_linked_folder': True, 'can_upload': False, 'upload_disabled_reason': LINKED_FOLDER_UPLOAD_DISABLED_REASON})
        if _is_artist_user(self.user):
            if not normalized_path or is_horizon_user_workspace_path(self.user, normalized_path):
                return self._list_artist_folder(project_dir, links, normalized_path, include_counts, folder_asset_by_path, folder_thumbnail_paths)
            if not can_access_horizon_folder_path(
                self.db,
                self.project_id,
                normalized_path,
                user=self.user,
                access_role=self.access_role,
            ):
                raise HTTPException(status_code=404, detail='Folder not found')
            items = self._list_project_fs(
                project_dir,
                links,
                normalized_path,
                include_counts,
                folder_asset_by_path,
                folder_thumbnail_paths,
                allowed_virtual_root=normalized_path,
            )
            items.sort(key=lambda item: ({'folder': 0, 'file': 1}.get(item.get('type'), 99), item.get('name', '').lower()))
            return ContentListResult(
                normalized_path,
                items,
                build_project_breadcrumbs(normalized_path),
                folder_context={
                    'mode': 'project',
                    'is_linked_folder': False,
                    'can_upload': False,
                    'upload_disabled_reason': 'Referenced folders are view-only. Upload files inside your workspace.',
                },
            )
        items = self._list_project_fs(project_dir, links, normalized_path, include_counts, folder_asset_by_path, folder_thumbnail_paths)
        if not normalized_path:
            items.extend(build_page_content_item(page) for page in list_horizon_pages(self.db, self.project_id))
            existing_tracker_names = {item.get('name') for item in items if item.get('type') == 'tracker'}
            for tracker in list_horizon_trackers(self.db, self.project_id):
                if tracker.name not in existing_tracker_names:
                    items.append({'id': tracker.id, 'slug': tracker.slug, 'name': tracker.name, 'path': tracker.id, 'type': 'tracker', 'shot_count': len(list_visible_horizon_shots(self.db, self.project_id, tracker_id=tracker.id, user=self.user, access_role=self.access_role)), 'last_activity_at': tracker.last_activity_at, 'source': 'horizons_db'})
        append_horizon_asset_virtual_items(items, self.db, self.project_id, folder_visible_assets, normalized_path, include_counts=include_counts, folder_thumbnail_paths=folder_thumbnail_paths)
        items.sort(key=lambda item: ({'page': 0, 'folder': 1, 'tracker': 2, 'file': 3}.get(item.get('type'), 99), item.get('name', '').lower()))
        read_only = project_storage_is_read_only(self.project)
        return ContentListResult(normalized_path, items, build_project_breadcrumbs(normalized_path), folder_context={'mode': 'project', 'is_linked_folder': False, 'can_upload': not read_only, 'upload_disabled_reason': 'This project storage location is read-only.' if read_only else ''})

    def _workspace_path(self) -> str:
        from app.services.horizons.team import ensure_horizon_project_user_workspace
        return ensure_horizon_project_user_workspace(self.db, self.project_id, self.user)

    def _list_artist_folder(self, project_dir: Path, links: list[dict], normalized_path: str, include_counts: bool, folder_asset_by_path: dict[str, object], folder_thumbnail_paths: set[str]) -> ContentListResult:
        workspace_path = self._workspace_path()
        workspace_dir = project_dir / workspace_path
        verify_path_in_project(workspace_dir, project_dir)
        if not normalized_path:
            item_count = count_project_folder_items(project_dir, workspace_path, links, include_counts=include_counts)
            item = {'name': Path(workspace_path).name, 'path': workspace_path, 'type': 'folder', 'item_count': item_count, 'is_workspace': True, 'custom_thumbnail': workspace_path in folder_thumbnail_paths, **_folder_time_metadata(workspace_dir)}
            return ContentListResult('', [item], build_project_breadcrumbs(''), folder_context={'mode': 'project', 'is_linked_folder': False, 'can_upload': False, 'upload_disabled_reason': 'Open your workspace folder to upload files.'})
        if not is_horizon_user_workspace_path(self.user, normalized_path):
            raise HTTPException(status_code=404, detail='Folder not found')
        items = self._list_project_fs(project_dir, links, normalized_path, include_counts, folder_asset_by_path, folder_thumbnail_paths, allowed_virtual_root=workspace_path)
        if normalized_path == workspace_path:
            _append_workspace_tracker_shortcuts(self.db, self.project_id, items, user=self.user, access_role=self.access_role)
        items.sort(key=lambda item: ({'folder': 0, 'tracker': 1, 'file': 2}.get(item.get('type'), 99), item.get('name', '').lower()))
        read_only = project_storage_is_read_only(self.project)
        return ContentListResult(normalized_path, items, build_project_breadcrumbs(normalized_path), folder_context={'mode': 'project', 'is_linked_folder': False, 'can_upload': not read_only, 'upload_disabled_reason': 'This project storage location is read-only.' if read_only else ''})

    def _list_project_fs(self, project_dir: Path, links: list[dict], normalized_path: str, include_counts: bool, folder_asset_by_path: dict[str, object], folder_thumbnail_paths: set[str], allowed_virtual_root: str | None = None) -> list[dict]:
        target_dir = project_dir / normalized_path if normalized_path else project_dir
        verify_path_in_project(target_dir, project_dir)
        read_only = project_storage_is_read_only(self.project)
        if _is_artist_user(self.user) and not read_only:
            target_dir.mkdir(parents=True, exist_ok=True)
            make_project_path_smb_mutable(target_dir)
        items: list[dict] = []
        if target_dir.exists() and target_dir.is_dir():
            for entry in sorted(target_dir.iterdir(), key=lambda item: (item.is_symlink() or not item.is_dir(), item.name.lower())):
                if entry.is_symlink() or entry.name.startswith('.') or entry.name == 'project.json':
                    continue
                rel_path = str(entry.relative_to(project_dir))
                if entry.is_dir():
                    items.append({'name': entry.name, 'path': rel_path, 'type': 'folder', 'item_count': count_project_folder_items(project_dir, rel_path, links, include_counts=include_counts), 'is_workspace': is_horizon_workspace_root_path(rel_path), 'custom_thumbnail': rel_path in folder_thumbnail_paths, **_folder_time_metadata(entry)})
                elif not entry.name.endswith('.tracker.json'):
                    asset = folder_asset_by_path.get(rel_path)
                    if not read_only:
                        asset = register_media_asset(self.db, self.project_id, rel_path, storage_scope='project') or asset
                    item = build_project_file_info_payload(self.project_id, rel_path, entry, db=self.db, asset=asset)
                    item['is_linked'] = False
                    items.append(item)
        append_linked_project_items(self.db, self.project_id, items, links, normalized_path, include_counts=include_counts, folder_thumbnail_paths=folder_thumbnail_paths, allowed_virtual_root=allowed_virtual_root)
        return items

    def resolve(self, ref: ContentRef, *, purpose: str) -> ResolvedContent:
        return _resolve_horizons_object(self.db, self.project_id, ref, detail='Horizons media asset not found', user=self.user, access_role=self.access_role)

    def collect_zip_entries(self, request: AuthorizedZipRequest) -> list[ZipEntry]:
        entries: list[ZipEntry] = []
        for ref in request.refs:
            entries.extend(collect_project_virtual_zip_entries(self.project_id, [ref.path], db=self.db, budget=request.budget, discovered_identities=request.discovered_identities))
        return entries


class LegacyProjectAuthPolicy(HorizonsProjectAuthPolicy):
    name = 'legacy_project_auth'

    def __init__(self, db: Session, project_id: str, user: dict | None, access_role: str | None):
        self.db = db
        self.project_id = project_id
        self.user = user
        self.access_role = access_role
        self.project = None
        self.project_dir = get_project_dir(project_id)

    def resolve(self, ref: ContentRef, *, purpose: str) -> ResolvedContent:
        if not ref.path:
            return super().resolve(ref, purpose=purpose)
        full_path, cache_key, storage_scope = resolve_project_link_target(self.project_id, ref.path)
        if full_path and full_path.exists():
            payload = build_project_file_info_payload(self.project_id, ref.path, full_path, db=self.db, storage_scope=storage_scope)
            return ResolvedContent(ref, full_path, True, cache_key, storage_scope, canonical_path=ref.path, physical_root=get_project_dir(self.project_id), payload=payload)
        full_path, cache_key, storage_scope = resolve_authorized_legacy_project_media_target(self.project_id, ref.path, self.user)
        return ResolvedContent(ref, full_path, bool(full_path and full_path.exists()), cache_key, storage_scope, canonical_path=ref.path, physical_root=get_project_dir(self.project_id))

    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]:
        return [ContentRef(namespace='legacy_project', project_id=self.project_id, path=self.normalize_request_path(path, allow_empty=False)) for path in raw_paths]

class NasAuthPolicy:
    name = 'nas_auth'

    def __init__(self, user: dict):
        self.user = user

    def normalize_request_path(self, raw_path: str | None, *, allow_empty: bool = True) -> str:
        return normalize_virtual_path(raw_path, allow_empty=allow_empty)

    def assert_can_list(self, path: str) -> None: return None
    def assert_can_resolve(self, ref: ContentRef, *, purpose: Literal['metadata', 'stream', 'thumbnail', 'download', 'zip']) -> ContentRef: return ref
    def list_folder(self, path: str, *, include_counts: bool = False) -> ContentListResult: raise NotImplementedError
    def resolve(self, ref: ContentRef, *, purpose: str) -> ResolvedContent:
        full_path = get_safe_path(ref.path)
        return ResolvedContent(ref, full_path, full_path.exists(), str(full_path), None, canonical_path=ref.path, physical_root=settings.MEDIA_ROOT)

    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]:
        refs = []
        for raw in raw_paths:
            try:
                path = self.normalize_request_path(raw, allow_empty=False)
                if not check_folder_read_permission(self.user, path):
                    continue
                refs.append(ContentRef(namespace='nas', path=path))
            except Exception:
                continue
        return refs

    def collect_zip_entries(self, request: AuthorizedZipRequest) -> list[ZipEntry]:
        entries: list[ZipEntry] = []
        used_roots: set[str] = set()
        for ref in request.refs:
            full_path = get_safe_path(ref.path)
            if not full_path.exists():
                continue
            arc_root = unique_arcname(full_path.name or 'folder', used_roots)
            entries.extend(collect_boundary_zip_entries(full_path, arc_root, physical_root=settings.MEDIA_ROOT, budget=request.budget, charge_root=True, discovered_identities=request.discovered_identities))
        return entries


def _horizons_virtual_folder_exists(project_id: str, path: str, db: Session) -> bool:
    normalized_path = normalize_virtual_path(path, allow_empty=True)
    prefix = f'{normalized_path}/'
    return bool(normalized_path) and any(normalize_virtual_path(asset.file_path, allow_empty=True).startswith(prefix) for asset in list_visible_horizon_media_assets(db, project_id) if getattr(asset, 'file_path', None) and getattr(asset, 'storage_scope', None) != 'media_root')

def _list_shared_project_contents(db: Session, share, path: str, *, include_counts: bool = False) -> ContentListResult:
    project = get_horizon_project(db, share.project_id)
    project_dir = resolve_project_root(project)
    held_asset_ids = (
        held_media_asset_ids_for_project(db, share.project_id)
        if share.share_type in {'project', 'project-folder', 'project-file', 'page'}
        else set()
    )
    held_paths = (
        held_media_paths_for_project(db, share.project_id)
        if held_asset_ids
        else set()
    )

    def item_is_held(item: dict) -> bool:
        item_asset_id = str(item.get('horizons_media_asset_id') or item.get('media_asset_id') or '')
        if item_asset_id in held_asset_ids:
            return True
        source_path = str(item.get('source_path') or '').strip()
        if not source_path:
            return False
        try:
            resolved_source, _cache_key, _scope = resolve_media_target(
                source_path,
                share.project_id,
                item.get('storage_scope'),
                db=db,
            )
            if resolved_source is None:
                return False
            resolved_source = resolved_source.resolve(strict=False)
            return resolved_source in held_paths
        except Exception:
            return False

    def asset_is_held(asset: MediaAsset) -> bool:
        if str(asset.id) in held_asset_ids:
            return True
        full_path, _cache_key, _scope = resolve_media_asset_path(
            asset,
            project_id=share.project_id,
            db=db,
        )
        return bool(
            full_path
            and full_path.resolve(strict=False) in held_paths
        )
    links = load_project_links(share.project_id).get('links', []) or []
    linked_folder_items = build_linked_folder_items(links, path, include_counts=include_counts, db=db, project_id=share.project_id)
    target = project_dir / path if path else project_dir
    verify_path_in_project(target, project_dir)
    allow_virtual_folder = bool(path and _horizons_virtual_folder_exists(share.project_id, path, db))
    if (not target.exists() or not target.is_dir()) and not allow_virtual_folder and linked_folder_items is None:
        raise HTTPException(status_code=404, detail='Folder not found')
    if linked_folder_items is not None:
        visible_linked_items = [
            item
            for item in linked_folder_items
            if not item_is_held(item)
        ]
        return ContentListResult(path, visible_linked_items, share_root=share.path if share.share_type == 'project-folder' else '')
    shared_page = get_horizon_page_by_ref(db, share.project_id, share.page_id or '') if share.share_type == 'page' else None
    items: list[dict] = []
    if target.exists() and target.is_dir():
        for entry in sorted(target.iterdir(), key=lambda item: (item.is_symlink() or not item.is_dir(), item.name.lower())):
            if entry.is_symlink() or entry.name.startswith('.') or entry.name in HIDDEN_SHARED_FOLDERS or entry.name == 'project.json':
                continue
            rel_path = str(entry.relative_to(project_dir))
            if entry.is_dir():
                items.append({'name': entry.name, 'path': rel_path, 'type': 'folder', 'item_count': count_project_folder_items(project_dir, rel_path, links, include_counts=include_counts)})
            elif entry.name.endswith('.tracker.json'):
                tracker_name = entry.stem.replace('.tracker', '')
                try:
                    tracker = json.loads(entry.read_text())
                    items.append({'name': tracker_name, 'path': rel_path, 'type': 'tracker', 'shot_count': len(tracker.get('shots', []))})
                except Exception:
                    pass
            else:
                horizon_asset = get_horizon_media_asset_by_path(db, share.project_id, rel_path)
                if horizon_asset and str(horizon_asset.id) in held_asset_ids:
                    continue
                if not horizon_asset and not (shared_page and page_allows_path(shared_page, rel_path)):
                    continue
                item = build_project_file_info_payload(share.project_id, rel_path, entry, db=db, asset=horizon_asset)
                item['is_linked'] = False
                items.append(item)
    append_linked_project_items(db, share.project_id, items, links, path, include_counts=include_counts, probe_video_duration=True)
    items[:] = [
        item
        for item in items
        if not item_is_held(item)
    ]
    visible_assets = [
        asset
        for asset in list_visible_horizon_media_assets(db, share.project_id)
        if not asset_is_held(asset)
    ]
    append_horizon_asset_virtual_items(items, db, share.project_id, visible_assets, path, include_counts=include_counts)
    return ContentListResult(path, items, share_root=share.path if share.share_type == 'project-folder' else '')

def _resolve_horizons_object(db: Session, project_id: str, ref: ContentRef, *, detail: str, user=None, access_role: str | None = None) -> ResolvedContent:
    full_path, cache_key, storage_scope, resolved_asset_id, canonical_path = _resolve_horizons_media_target_by_refs(db, project_id, horizons_media_asset_id=ref.media_asset_id, horizons_shot_version_id=ref.shot_version_id)
    if not canonical_path or not resolved_asset_id:
        raise HTTPException(status_code=404, detail=detail)
    if user is not None:
        visible = can_access_horizon_shot_version_id(db, project_id, ref.shot_version_id, user=user, access_role=access_role) if ref.shot_version_id else can_access_horizon_media_asset_id(db, project_id, resolved_asset_id, user=user, access_role=access_role)
        if not visible:
            raise HTTPException(status_code=404, detail=detail)
    asset = db.query(MediaAsset).filter(MediaAsset.id == resolved_asset_id).filter(MediaAsset.project_id == project_id).first()
    if asset is None:
        raise HTTPException(status_code=404, detail=detail)
    payload = build_project_file_info_payload(project_id, canonical_path, full_path, db=db, storage_scope=storage_scope, asset=asset, exists=bool(full_path and full_path.exists()))
    if ref.shot_version_id is None:
        payload.pop('version_id', None)
        payload.pop('horizons_shot_version_id', None)
    payload = attach_canonical_media_identity(payload, media_asset_id=resolved_asset_id, shot_version_id=ref.shot_version_id)
    return ResolvedContent(ref, full_path, bool(full_path and full_path.exists()), cache_key, storage_scope, media_asset_id=resolved_asset_id, shot_version_id=ref.shot_version_id, canonical_path=canonical_path, physical_root=resolve_project_root(get_horizon_project(db, project_id)), payload=payload)

def resolve_horizons_object_auth(db: Session, project_id: str, *, asset_id: str | None = None, version_id: str | None = None, detail: str, user=None, access_role: str | None = None) -> ResolvedContent:
    ref = ContentRef(namespace='horizons_shot_version' if version_id else 'horizons_media_asset', project_id=project_id, media_asset_id=asset_id, shot_version_id=version_id)
    return _resolve_horizons_object(db, project_id, ref, detail=detail, user=user, access_role=access_role)

def resolve_horizons_object_share(share, db: Session, *, asset_id: str | None = None, version_id: str | None = None) -> ResolvedContent:
    full_path, cache_key, storage_scope, resolved_asset_id, canonical_path = resolve_shared_horizons_object_target(share, db, horizons_media_asset_id=asset_id, horizons_shot_version_id=version_id)
    asset = db.query(MediaAsset).filter(MediaAsset.id == resolved_asset_id).first() if resolved_asset_id else None
    payload = build_project_file_info_payload(share.project_id, canonical_path, full_path, db=db, storage_scope=storage_scope, asset=asset, exists=bool(full_path and full_path.exists()))
    if version_id is None:
        payload.pop('version_id', None)
        payload.pop('horizons_shot_version_id', None)
    payload = attach_canonical_media_identity(payload, media_asset_id=resolved_asset_id, shot_version_id=version_id)
    ref = ContentRef(namespace='horizons_shot_version' if version_id else 'horizons_media_asset', project_id=share.project_id, share_id=share.id, media_asset_id=asset_id, shot_version_id=version_id)
    return ResolvedContent(ref, full_path, bool(full_path and full_path.exists()), cache_key, storage_scope, media_asset_id=resolved_asset_id, shot_version_id=version_id, canonical_path=canonical_path, physical_root=resolve_project_root(get_horizon_project(db, share.project_id)), payload=payload)

def object_payload_tuple(resolved: ResolvedContent):
    return resolved.full_path, resolved.cache_identity, resolved.payload

def list_content(policy: ContentAccessPolicy, path: str, *, include_counts: bool = False) -> ContentListResult:
    normalized = policy.normalize_request_path(path, allow_empty=True)
    policy.assert_can_list(normalized)
    return policy.list_folder(normalized, include_counts=include_counts)
def resolve_content(policy: ContentAccessPolicy, ref: ContentRef, *, purpose: str) -> ResolvedContent:
    checked = policy.assert_can_resolve(ref, purpose=purpose)
    return policy.resolve(checked, purpose=purpose)

def collect_zip(policy: ContentAccessPolicy, raw_paths: list[str]) -> list[ZipEntry]:
    budget = new_zip_discovery_budget()
    refs = policy.assert_can_zip_roots(raw_paths)
    request = AuthorizedZipRequest(refs=refs, budget=budget, discovered_identities=set())
    entries = policy.collect_zip_entries(request)
    if not entries:
        raise HTTPException(status_code=404, detail='No files found')
    return entries
