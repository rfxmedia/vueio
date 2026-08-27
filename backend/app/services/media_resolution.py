from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.services.media import get_file_hash, get_safe_path
from app.services.project_access import verify_path_in_project
from app.services.project_links import find_link_target, join_rel_path, link_storage_scope
from app.services.projects import get_project_dir, load_project_links, resolve_horizon_project_root, resolve_project_root_by_id

settings = get_settings()
STORAGE_SCOPE_ALIASES = {
    'nas': 'media_root',
    'linked_media': 'media_root',
    'file_browser': 'media_root',
}
MEDIA_ROOT_SCOPES = {'media_root'}
PROJECT_ROOT_SCOPES = {'project'}
HEURISTIC_SCOPES = {'tracker_version', 'horizons_declared'}


def normalize_storage_scope(storage_scope: str | None) -> str | None:
    value = (storage_scope or '').strip().lower()
    if not value:
        return None
    return STORAGE_SCOPE_ALIASES.get(value, value)


def _resolve_project_path(project_id: str | None, file_path: str, *, db=None) -> tuple[Path | None, str | None, str | None]:
    if not project_id or not file_path:
        return None, None, None
    if db is not None:
        from app.models import HorizonProject

        # Configured projects must fail closed when their selected storage root
        # is unavailable. Projects that genuinely predate the database-backed
        # model still live under app data and retain their original resolver.
        if db.get(HorizonProject, project_id) is not None:
            project_dir = resolve_horizon_project_root(db, project_id)
        else:
            project_dir = get_project_dir(project_id)
    else:
        project_dir = resolve_project_root_by_id(project_id)
    try:
        project_path = project_dir / file_path
        verify_path_in_project(project_path, project_dir)
        if project_path.exists():
            return project_path, f'project:{project_id}:{file_path}', 'project'
    except Exception:
        pass
    return None, None, None


def _resolve_media_root_path(file_path: str) -> tuple[Path | None, str | None, str | None]:
    if not file_path:
        return None, None, None
    try:
        safe_path = get_safe_path(file_path)
        if safe_path.exists():
            return safe_path, media_root_cache_identity(file_path), 'media_root'
    except Exception:
        pass
    return None, None, None


def resolve_media_target(file_path: str, project_id: Optional[str] = None, storage_scope: str | None = None, *, db=None) -> tuple[Path | None, str | None, str | None]:
    if not file_path:
        return None, None, None

    normalized_scope = normalize_storage_scope(storage_scope)
    if normalized_scope in PROJECT_ROOT_SCOPES:
        return _resolve_project_path(project_id, file_path, db=db)
    if normalized_scope in MEDIA_ROOT_SCOPES:
        return _resolve_media_root_path(file_path)

    project_path, project_key, project_scope = _resolve_project_path(project_id, file_path, db=db)
    if project_path:
        return project_path, project_key, project_scope

    media_path, media_key, media_scope = _resolve_media_root_path(file_path)
    if media_path:
        return media_path, media_key, media_scope

    return None, None, normalized_scope if normalized_scope in HEURISTIC_SCOPES else None


def get_media_cache_identity(
    project_id: str | None,
    file_path: str,
    full_path: Path,
    *,
    storage_scope: str | None = None,
    asset_id: str | None = None,
    resolved_job_key: str | None = None,
) -> str:
    normalized_scope = normalize_storage_scope(storage_scope)
    if normalized_scope in MEDIA_ROOT_SCOPES:
        try:
            return media_source_cache_identity(source_signature(full_path))
        except OSError:
            return resolved_job_key or media_root_cache_identity(file_path)
    if asset_id:
        try:
            generation = source_signature(full_path)
        except OSError:
            generation = None
        if generation:
            return media_source_cache_identity(generation)
        return f'asset:{asset_id}'
    if resolved_job_key:
        try:
            return media_source_cache_identity(source_signature(full_path))
        except OSError:
            return resolved_job_key

    if normalized_scope == 'project' and project_id:
        try:
            return f'project:{project_id}:source:{source_signature(full_path)}:{file_path}'
        except OSError:
            return f'project:{project_id}:{file_path}'
    if normalized_scope in MEDIA_ROOT_SCOPES:
        return media_root_cache_identity(file_path)

    if project_id:
        try:
            project_dir = resolve_project_root_by_id(project_id)
            full_path.resolve().relative_to(project_dir.resolve())
            return f'project:{project_id}:{file_path}'
        except Exception:
            pass
    try:
        return media_source_cache_identity(source_signature(full_path))
    except OSError:
        return media_root_cache_identity(file_path)


def resolve_media_asset_path(asset, project_id: Optional[str] = None, *, db=None) -> tuple[Path | None, str | None, str | None]:
    full_path, resolved_job_key, storage_scope = resolve_media_target(asset.file_path, project_id or getattr(asset, 'project_id', None), getattr(asset, 'storage_scope', None), db=db)
    if not full_path:
        if db is not None:
            from app.services.media_assets import validate_media_asset_source

            validate_media_asset_source(db, asset, None)
        return None, f'asset:{asset.id}', storage_scope
    if db is not None:
        from app.services.media_assets import validate_media_asset_source

        if not validate_media_asset_source(db, asset, full_path):
            return None, f'asset:{asset.id}', storage_scope
    elif getattr(asset, 'unavailable_at', None) is not None:
        return None, f'asset:{asset.id}', storage_scope
    cache_identity = str(getattr(asset, 'artifact_identity', '') or '').strip()
    source_generation = str(getattr(asset, 'source_signature', '') or '').strip()
    if source_generation and (not cache_identity or cache_identity.startswith('asset:')):
        cache_identity = media_source_cache_identity(source_generation)
    cache_identity = cache_identity or get_media_cache_identity(
        project_id or getattr(asset, 'project_id', None),
        getattr(asset, 'file_path', ''),
        full_path,
        storage_scope=storage_scope or getattr(asset, 'storage_scope', None),
        asset_id=getattr(asset, 'id', None),
        resolved_job_key=resolved_job_key,
    )
    return full_path, cache_identity, storage_scope


def resolve_project_link_target(project_id: str, virtual_path: str) -> tuple[Path | None, str | None, str | None]:
    match = find_link_target(load_project_links(project_id).get('links', []), virtual_path)
    if not match:
        return None, None, None
    link, suffix = match
    source_path = str(link.get('source_path') or '').strip()
    if not source_path:
        return None, None, None
    target_path = join_rel_path(source_path, suffix) if suffix else source_path
    return resolve_media_target(target_path, project_id, link_storage_scope(link))


def resolve_project_content_target(project_id: str, path: str) -> tuple[Path | None, str | None, str | None]:
    linked_path, cache_key, storage_scope = resolve_project_link_target(project_id, path)
    if linked_path is not None and linked_path.is_file():
        return linked_path, cache_key, storage_scope

    normalized_path = str(path or '').strip().strip('/')
    for link in load_project_links(project_id).get('links', []) or []:
        source_path = str(link.get('source_path') or '').strip().strip('/')
        if not source_path:
            continue
        if normalized_path != source_path and not normalized_path.startswith(f'{source_path}/'):
            continue
        linked_source, cache_key, storage_scope = resolve_media_target(
            normalized_path,
            project_id,
            link_storage_scope(link),
        )
        if linked_source is not None and linked_source.is_file():
            return linked_source, cache_key, storage_scope

    project_path, cache_key, storage_scope = resolve_media_target(
        normalized_path,
        project_id,
        storage_scope='project',
    )
    if project_path is not None and project_path.is_file():
        return project_path, cache_key, storage_scope
    return None, None, storage_scope


def normalize_media_root_cache_path(file_path: str) -> str:
    return str(file_path or '').strip().lstrip('/')


def media_root_cache_identity(file_path: str) -> str:
    return f'media_root:{normalize_media_root_cache_path(file_path)}'


def media_source_cache_identity(signature: str) -> str:
    return f'media_source:{signature}'


def stored_media_asset_cache_identity(asset) -> str:
    persisted = str(getattr(asset, 'artifact_identity', '') or '').strip()
    if persisted:
        return persisted
    asset_id = str(getattr(asset, 'id', '') or '').strip()
    signature = str(getattr(asset, 'source_signature', '') or '').strip()
    if signature:
        return media_source_cache_identity(signature)
    return f'asset:{asset_id}'


def legacy_media_source_identities(db, full_path: Path, canonical_identity: str) -> list[str]:
    """Return prior per-asset identities for this exact physical source."""
    try:
        generation = source_signature(full_path)
    except OSError:
        return []

    from app.models import MediaAsset

    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.source_signature == generation)
        .filter(MediaAsset.unavailable_at.is_(None))
        .all()
    )
    aliases: list[str] = []
    for asset in assets:
        aliases.extend((
            str(getattr(asset, 'artifact_identity', '') or '').strip(),
            f'asset:{asset.id}',
            f'asset:{asset.id}:source:{generation}',
        ))
    return list(dict.fromkeys(alias for alias in aliases if alias and alias != canonical_identity))


def source_signature(path: Path) -> str:
    stat = path.stat()
    payload = ':'.join(str(value) for value in (
        int(stat.st_size),
        int(getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1_000_000_000))),
        int(getattr(stat, 'st_ctime_ns', int(stat.st_ctime * 1_000_000_000))),
        int(getattr(stat, 'st_dev', 0)),
        int(getattr(stat, 'st_ino', 0)),
    ))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]


GENERATED_THUMBNAIL_CACHE_VERSION = 'thumb-v3-960w-square-pixels'
DELIVERY_POSTER_CACHE_VERSION = 'delivery-poster-v1-1920w-square-pixels'


def thumbnail_cache_path_for_identity(cache_identity: str) -> Path:
    return settings.thumbnail_dir / f'{get_file_hash(cache_identity)}.jpg'


def generated_thumbnail_cache_path_for_identity(cache_identity: str) -> Path:
    return thumbnail_cache_path_for_identity(f'{GENERATED_THUMBNAIL_CACHE_VERSION}:{cache_identity}')


def delivery_poster_cache_path_for_identity(cache_identity: str) -> Path:
    return thumbnail_cache_path_for_identity(f'{DELIVERY_POSTER_CACHE_VERSION}:{cache_identity}')


def thumbnail_cache_path_for_browser(file_path: str) -> Path:
    return generated_thumbnail_cache_path_for_identity(media_root_cache_identity(file_path))


def folder_thumbnail_cache_path(folder_path: str) -> Path:
    return thumbnail_cache_path_for_identity(f'folder_{folder_path}')


def thumbnail_cache_path_for_media(project_id: str | None, file_path: str, full_path: Path, storage_scope: str | None = None, *, asset_id: str | None = None, cache_identity: str | None = None) -> Path:
    thumb_id = get_media_cache_identity(
        project_id,
        file_path,
        full_path,
        storage_scope=storage_scope,
        asset_id=asset_id,
        resolved_job_key=cache_identity,
    )
    return generated_thumbnail_cache_path_for_identity(thumb_id)


def delivery_poster_cache_path_for_media(project_id: str | None, file_path: str, full_path: Path, storage_scope: str | None = None, *, asset_id: str | None = None, cache_identity: str | None = None) -> Path:
    poster_id = get_media_cache_identity(
        project_id,
        file_path,
        full_path,
        storage_scope=storage_scope,
        asset_id=asset_id,
        resolved_job_key=cache_identity,
    )
    return delivery_poster_cache_path_for_identity(poster_id)


def transcode_cache_path_for_identity(cache_identity: str) -> Path:
    return settings.transcode_dir / f'{get_file_hash(cache_identity)}.mp4'


def hls_package_id_for_identity(cache_identity: str) -> str:
    return get_file_hash(cache_identity)


def hls_package_dir_for_identity(cache_identity: str) -> Path:
    return settings.transcode_dir / hls_package_id_for_identity(cache_identity)


def hls_master_playlist_path_for_identity(cache_identity: str) -> Path:
    package_dir = hls_package_dir_for_identity(cache_identity)
    pointer_path = package_dir.with_name(f'{package_dir.name}.current.json')
    try:
        import json

        data = json.loads(pointer_path.read_text(encoding='utf-8'))
        package_name = str(data.get('package_dir') or '')
        if (
            package_name
            and '/' not in package_name
            and '\\' not in package_name
            and package_name.startswith(f'{package_dir.name}.')
            and package_name.endswith('.pkg')
        ):
            active_dir = (package_dir.parent / package_name).resolve()
            active_dir.relative_to(package_dir.parent.resolve())
            if active_dir.exists() and active_dir.is_dir():
                return active_dir / 'master.m3u8'
    except Exception:
        pass
    return package_dir / 'master.m3u8'


def resolve_media_full_path(file_path: str, project_id: Optional[str] = None, storage_scope: str | None = None) -> tuple[Path | None, str | None]:
    full_path, job_key, _storage_scope = resolve_media_target(file_path, project_id, storage_scope=storage_scope)
    return full_path, job_key
