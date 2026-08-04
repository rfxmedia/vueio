from __future__ import annotations

from pathlib import Path

from app.services.media import get_safe_path
from app.services.project_access import verify_path_in_project


def join_rel_path(base: str, name: str) -> str:
    if base is None:
        base = ''
    base = str(base)
    name = str(name or '').strip('/')
    if not base:
        return name
    leading = '/' if base.startswith('/') else ''
    stripped = base.strip('/')
    return f'{leading}{stripped}/{name}' if name else f'{leading}{stripped}'


def linked_virtual_root(link: dict) -> str:
    target = (link.get('target_folder') or '').strip('/')
    base = Path(str(link.get('source_path') or '')).name
    return join_rel_path(target, base).strip('/')


def link_storage_scope(link: dict) -> str:
    return 'project' if link.get('storage_scope') == 'project' else 'media_root'


def resolve_link_source_path(link: dict, *, project_root: Path | None = None, suffix: str = '') -> Path | None:
    source = str(link.get('source_path') or '').strip()
    if not source:
        return None
    source = join_rel_path(source, suffix) if suffix else source
    if link_storage_scope(link) == 'project':
        if project_root is None:
            return None
        path = project_root / source.strip('/')
        verify_path_in_project(path, project_root)
        return path
    return get_safe_path(source)


def find_link_by_virtual_path(links: list, virtual_path: str) -> dict | None:
    match = find_link_target(links, virtual_path)
    return match[0] if match else None


def find_link_target(links: list, virtual_path: str) -> tuple[dict, str] | None:
    if not virtual_path:
        return None
    vp = str(virtual_path).strip('/')
    for link in links or []:
        try:
            root = linked_virtual_root(link)
        except Exception:
            continue
        if root == vp:
            return link, ''
        if root and vp.startswith(f'{root}/'):
            return link, vp[len(root) + 1 :]
    return None


def linked_virtual_paths_for_source(links: list, source_path: str) -> list[str]:
    normalized_source = str(source_path or '').strip().strip('/')
    if not normalized_source:
        return []

    paths = []
    for link in links or []:
        linked_source = str(link.get('source_path') or '').strip().strip('/')
        if not linked_source:
            continue
        if normalized_source == linked_source:
            suffix = ''
        elif normalized_source.startswith(f'{linked_source}/'):
            suffix = normalized_source[len(linked_source) + 1:]
        else:
            continue
        virtual_path = join_rel_path(linked_virtual_root(link), suffix).strip('/')
        if virtual_path and virtual_path not in paths:
            paths.append(virtual_path)
    return paths


def _linked_scope_metadata(payload: dict, storage_scope: str) -> dict:
    return {
        **payload,
        'storage_scope': storage_scope,
        'kind': 'linked',
        'is_runtime': False,
        'is_declared': False,
        'is_linked': True,
        'is_generated': False,
    }


def merge_linked_path_metadata(metadata: dict, *, source_path: str, is_folder: bool, link_kind: str | None = None, storage_scope: str = 'media_root') -> dict:
    return _linked_scope_metadata({
        **metadata,
        'source_path': source_path,
        'full_path': source_path,
        'link_kind': link_kind or ('direct-folder' if is_folder else 'direct-file'),
    }, storage_scope)


def build_linked_folder_item(*, name: str, virtual_path: str, source_path: str, item_count: int | None, mtime: float | None = None, ctime: float | None = None, link_kind: str = 'direct-folder', storage_scope: str = 'media_root') -> dict:
    payload = {
        'name': name,
        'path': virtual_path,
        'type': 'folder',
        'item_count': item_count,
        'source_path': source_path,
        'full_path': source_path,
        'link_kind': link_kind,
    }
    if mtime is not None:
        payload['mtime'] = mtime
        payload['modified_at'] = mtime
    if ctime is not None:
        payload['ctime'] = ctime
        payload['created_at'] = ctime
    return _linked_scope_metadata(payload, storage_scope)


def build_linked_file_item(*, name: str, virtual_path: str, source_path: str, extension: str, size: int, size_formatted: str, mtime: float, ctime: float, is_video: bool, is_image: bool, is_pdf: bool, duration: float, duration_formatted: str, needs_transcode: bool, link_kind: str = 'direct-file', media_asset_id: str | None = None, storage_scope: str = 'media_root') -> dict:
    payload = _linked_scope_metadata({
        'name': name,
        'path': virtual_path,
        'source_path': source_path,
        'full_path': source_path,
        'type': 'file',
        'is_video': is_video,
        'is_image': is_image,
        'is_pdf': is_pdf,
        'link_kind': link_kind,
        'extension': extension,
        'size': size,
        'size_formatted': size_formatted,
        'mtime': mtime,
        'ctime': ctime,
        'duration': duration,
        'duration_formatted': duration_formatted,
        'needs_transcode': needs_transcode,
    }, storage_scope)
    if media_asset_id:
        payload.update({
            'media_asset_id': media_asset_id,
            'horizons_media_asset_id': media_asset_id,
            'media_entity_type': 'media_asset',
            'media_entity_id': media_asset_id,
            'media_entity_key': f'asset:{media_asset_id}',
        })
    return payload
