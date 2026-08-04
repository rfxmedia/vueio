from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import HTTPException
from sqlalchemy import or_

from app.services.media import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, format_size, get_safe_path, needs_transcode
from app.services.media_assets import escape_like_path, register_media_asset
from app.services.project_access import verify_path_in_project
from app.services.project_links import (
    build_linked_file_item,
    build_linked_folder_item,
    find_link_target,
    join_rel_path,
    linked_virtual_root,
    link_storage_scope,
    resolve_link_source_path,
)
from app.services.projects import get_project_dir, load_project_links, resolve_horizon_project_root
from app.services.share_access import normalize_virtual_path as normalize_strict_virtual_path
from app.services.zip_utils import ZipDiscoveryBudget, ZipEntry, ZipFileIdentity, collect_boundary_zip_entries, new_zip_discovery_budget

PDF_EXTENSIONS = {'.pdf'}


def normalize_virtual_path(path: str | None) -> str:
    return normalize_strict_virtual_path(path, allow_empty=True)


def link_target_folder(link: dict) -> str:
    return normalize_virtual_path(link.get('target_folder'))


def links_in_virtual_folder(links: list, folder_path: str | None) -> list[dict]:
    normalized = normalize_virtual_path(folder_path)
    return [
        link
        for link in links or []
        if link_target_folder(link) == normalized
    ]


def _resolve_link_source(link: dict, project_dir: Path, suffix: str = '') -> Path | None:
    try:
        return resolve_link_source_path(link, project_root=project_dir, suffix=suffix)
    except Exception:
        return None


def count_links_in_virtual_folder(links: list, folder_path: str | None, project_dir: Path) -> int:
    count = 0
    for link in links_in_virtual_folder(links, folder_path):
        source_path = _resolve_link_source(link, project_dir)
        if source_path and source_path.exists():
            count += 1
    return count


def _is_countable_project_entry(entry: Path) -> bool:
    return (
        not entry.is_symlink()
        and not entry.name.startswith('.')
        and entry.name != 'project.json'
        and not entry.name.endswith('.tracker.json')
    )


def count_project_folder_items(project_dir: Path, folder_path: str | None, links: list, *, include_counts: bool) -> int | None:
    if not include_counts:
        return None
    normalized = normalize_virtual_path(folder_path)
    target_dir = project_dir / normalized if normalized else project_dir
    count = 0
    try:
        if target_dir.exists() and target_dir.is_dir():
            count = sum(1 for entry in target_dir.iterdir() if _is_countable_project_entry(entry))
    except Exception:
        count = 0
    return count + count_links_in_virtual_folder(links, normalized, project_dir)


def build_linked_folder_items(links: list, folder_path: str | None, *, include_counts: bool = False, folder_thumbnail_paths: set[str] | None = None, db=None, project_id: str | None = None) -> list[dict] | None:
    normalized = normalize_virtual_path(folder_path)
    if not normalized:
        return None

    match = find_link_target(links or [], normalized)
    if not match:
        return None

    link, suffix = match
    if (link.get('type') or 'file') != 'folder':
        return None

    linked_source = str(link.get('source_path') or '').strip()
    if not linked_source:
        raise HTTPException(status_code=404, detail='Linked folder not found')

    project_dir = resolve_horizon_project_root(db, project_id) if db is not None and project_id else get_project_dir(project_id or '')
    source_rel = join_rel_path(linked_source, suffix) if suffix else linked_source
    source_dir = _resolve_link_source(link, project_dir, suffix)
    if source_dir is None or not source_dir.exists() or not source_dir.is_dir():
        raise HTTPException(status_code=404, detail='Linked folder not found')

    thumbnail_paths = folder_thumbnail_paths or set()
    storage_scope = link_storage_scope(link)
    items: list[dict] = []
    for entry in sorted(source_dir.iterdir(), key=lambda item: (item.is_symlink() or not item.is_dir(), item.name.lower())):
        if entry.is_symlink() or entry.name.startswith('.'):
            continue
        child_virtual_path = join_rel_path(normalized, entry.name).strip('/')
        child_source_path = join_rel_path(source_rel, entry.name)
        if entry.is_dir():
            stat = entry.stat()
            created_at = getattr(stat, 'st_birthtime', stat.st_ctime)
            item_count = None
            if include_counts:
                try:
                    item_count = sum(1 for child in entry.iterdir() if not child.is_symlink() and not child.name.startswith('.'))
                except Exception:
                    item_count = 0
            folder_item = build_linked_folder_item(
                name=entry.name,
                virtual_path=child_virtual_path,
                source_path=child_source_path,
                item_count=item_count,
                mtime=stat.st_mtime,
                ctime=created_at,
                link_kind='folder-child',
                storage_scope=storage_scope,
            )
            folder_item['custom_thumbnail'] = child_virtual_path in thumbnail_paths
            items.append(folder_item)
            continue

        stat = entry.stat()
        ext = entry.suffix.lower()
        is_video = ext in VIDEO_EXTENSIONS
        created_at = getattr(stat, 'st_birthtime', stat.st_ctime)
        asset = register_media_asset(db, project_id, child_source_path, storage_scope=storage_scope, commit=False) if db is not None else None
        items.append(build_linked_file_item(
            name=entry.name,
            virtual_path=child_virtual_path,
            source_path=child_source_path,
            extension=ext.lstrip('.'),
            size=stat.st_size,
            size_formatted=format_size(stat.st_size),
            mtime=stat.st_mtime,
            ctime=created_at,
            is_video=is_video,
            is_image=ext in IMAGE_EXTENSIONS,
            is_pdf=ext in PDF_EXTENSIONS,
            duration=0,
            duration_formatted='',
            needs_transcode=needs_transcode(entry) if is_video else False,
            link_kind='folder-child',
            media_asset_id=asset.id if asset else None,
            storage_scope=storage_scope,
        ))
    if db is not None:
        db.commit()
    return items


def _zip_arc_root(virtual_path: str, fallback: str) -> str:
    normalized = normalize_virtual_path(virtual_path)
    name = PurePosixPath(normalized).name if normalized else ''
    return name or fallback or 'folder'


def _append_fs_zip_entries(
    entries: list[ZipEntry],
    source_path: Path,
    arc_root: str,
    *,
    physical_root: Path,
    budget: ZipDiscoveryBudget,
    discovered_identities: set[ZipFileIdentity],
    excluded_paths: set[Path],
) -> None:
    entries.extend(collect_boundary_zip_entries(
        source_path,
        arc_root,
        physical_root=physical_root,
        budget=budget,
        charge_root=False,
        discovered_identities=discovered_identities,
        excluded_paths=excluded_paths,
    ))


def _append_links_under_folder(
    entries: list[ZipEntry],
    links: list,
    folder_path: str,
    arc_root: str,
    *,
    budget: ZipDiscoveryBudget,
    discovered_identities: set[ZipFileIdentity],
    excluded_paths: set[Path],
    project_dir: Path,
) -> None:
    normalized = normalize_virtual_path(folder_path)
    prefix = f'{normalized}/' if normalized else ''
    for link in links or []:
        try:
            virtual_root = linked_virtual_root(link)
        except Exception:
            continue
        if normalized:
            if virtual_root == normalized:
                rel_arc = PurePosixPath(PurePosixPath(virtual_root).name or 'file')
            elif virtual_root.startswith(prefix):
                rel_arc = PurePosixPath(virtual_root[len(prefix):])
            else:
                continue
        else:
            rel_arc = PurePosixPath(virtual_root)

        source_path = _resolve_link_source(link, project_dir)
        if not source_path or not source_path.exists():
            continue
        _append_fs_zip_entries(
            entries,
            source_path,
            str(PurePosixPath(arc_root) / rel_arc),
            physical_root=source_path,
            budget=budget,
            discovered_identities=discovered_identities,
            excluded_paths=excluded_paths,
        )


def _append_horizon_asset_zip_entries(
    entries: list[ZipEntry],
    db,
    project_id: str,
    folder_path: str,
    arc_root: str,
    *,
    budget: ZipDiscoveryBudget,
    discovered_identities: set[ZipFileIdentity],
    excluded_paths: set[Path],
) -> None:
    if db is None:
        return
    from app.models import MediaAsset
    from app.services.media_resolution import resolve_media_asset_path

    normalized = normalize_virtual_path(folder_path)
    prefix = f'{normalized}/' if normalized else ''
    query = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.unavailable_at.is_(None))
        .order_by(MediaAsset.created_at.asc(), MediaAsset.id.asc())
    )
    if normalized:
        like_prefix = f'{escape_like_path(normalized)}/%'
        query = query.filter(or_(MediaAsset.file_path == normalized, MediaAsset.file_path.like(like_prefix, escape='\\')))
    try:
        assets = query.yield_per(100)
    except Exception:
        assets = query

    for asset in assets:
        asset_path = normalize_virtual_path(getattr(asset, 'file_path', ''))
        if not asset_path:
            continue
        if normalized:
            if asset_path == normalized:
                rel_arc = None
            elif asset_path.startswith(prefix):
                rel_arc = PurePosixPath(asset_path[len(prefix):])
            else:
                continue
        else:
            rel_arc = PurePosixPath(asset_path)
        full_path, _cache_key, scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
        boundary = get_safe_path('') if scope == 'media_root' else resolve_horizon_project_root(db, project_id)
        if full_path and full_path.exists() and full_path.is_file():
            arcname = str(PurePosixPath(arc_root) / rel_arc) if rel_arc is not None else arc_root
            entries.extend(collect_boundary_zip_entries(
                full_path,
                arcname,
                physical_root=boundary,
                budget=budget,
                charge_root=False,
                discovered_identities=discovered_identities,
                excluded_paths=excluded_paths,
            ))


def collect_project_virtual_zip_entries(
    project_id: str,
    virtual_paths: list[str],
    *,
    db=None,
    budget: ZipDiscoveryBudget | None = None,
    discovered_identities: set[ZipFileIdentity] | None = None,
    excluded_paths: set[Path] | None = None,
) -> list[ZipEntry]:
    project_dir = resolve_horizon_project_root(db, project_id) if db is not None else get_project_dir(project_id)
    links = load_project_links(project_id).get('links', []) or []
    discovery_budget = budget or new_zip_discovery_budget()
    physical_identities = discovered_identities if discovered_identities is not None else set()
    resolved_exclusions = {
        path.resolve(strict=False)
        for path in (excluded_paths or set())
    }
    entries: list[ZipEntry] = []

    for raw_path in virtual_paths or []:
        discovery_budget.charge_requested_root()
        virtual_path = normalize_virtual_path(raw_path)
        linked_match = find_link_target(links, virtual_path) if virtual_path else None
        if linked_match:
            link, suffix = linked_match
            source_root = str(link.get('source_path') or '').strip()
            if source_root:
                source_path = _resolve_link_source(link, project_dir, suffix)
                if source_path is not None and source_path.exists():
                    linked_root = _resolve_link_source(link, project_dir)
                    if linked_root is not None:
                        _append_fs_zip_entries(
                            entries,
                            source_path,
                            _zip_arc_root(virtual_path, source_path.name),
                            physical_root=linked_root,
                            budget=discovery_budget,
                            discovered_identities=physical_identities,
                            excluded_paths=resolved_exclusions,
                        )
            continue

        project_path = project_dir / virtual_path if virtual_path else project_dir
        verify_path_in_project(project_path, project_dir)
        project_exists = project_path.exists()
        if project_exists:
            _append_fs_zip_entries(
                entries,
                project_path,
                _zip_arc_root(virtual_path, project_path.name),
                physical_root=project_dir,
                budget=discovery_budget,
                discovered_identities=physical_identities,
                excluded_paths=resolved_exclusions,
            )
        if project_path.is_dir() or (project_exists and not project_path.is_file()) or not project_exists:
            arc_root = _zip_arc_root(virtual_path, project_path.name if project_exists else 'folder')
            _append_links_under_folder(
                entries,
                links,
                virtual_path,
                arc_root,
                budget=discovery_budget,
                discovered_identities=physical_identities,
                excluded_paths=resolved_exclusions,
                project_dir=project_dir,
            )
            _append_horizon_asset_zip_entries(
                entries,
                db,
                project_id,
                virtual_path,
                arc_root,
                budget=discovery_budget,
                discovered_identities=physical_identities,
                excluded_paths=resolved_exclusions,
            )

    return entries
