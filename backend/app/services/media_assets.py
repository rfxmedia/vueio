from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Comment,
    HorizonProject,
    HorizonShot,
    HorizonShotVersion,
    MediaAsset,
    MediaMetadata,
    ShareLink,
    ShotRegistryEntry,
    VersionRegistryEntry,
)
from app.services.media_resolution import media_source_cache_identity, normalize_storage_scope as normalize_resolved_storage_scope, resolve_media_target, source_signature
from app.services.trackers import get_tracker_write_lock, load_tracker, save_tracker

RUNTIME_STORAGE_SCOPES = {'project', 'tracker_version'}
DECLARED_STORAGE_SCOPES = {'horizons_declared'}
LINKED_STORAGE_SCOPES = {'media_root'}
GENERATED_STORAGE_SCOPES = {'derived_artifact', 'transcode', 'thumbnail'}
GLOBAL_MEDIA_PROJECT_ID = '__media_root__'
UNIQUE_BINDING_RETRY_LIMIT = 3
ACTIVE_BINDING_CONSTRAINT_NAME = 'uq_media_assets_active_owner_scope_path'
SQLITE_ACTIVE_BINDING_SIGNATURE = 'UNIQUE constraint failed: media_assets.project_id, media_assets.storage_scope, media_assets.file_path'
SOURCE_FINGERPRINT_ALGORITHM = 'sampled-sha256-v1'
SOURCE_FINGERPRINT_BYTES = 4 * 1024 * 1024
SOURCE_FINGERPRINT_SAMPLES = 16


def escape_like_path(value: str) -> str:
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _is_active_binding_integrity_error(exc: IntegrityError) -> bool:
    orig = getattr(exc, 'orig', None)
    diag = getattr(orig, 'diag', None)
    if getattr(diag, 'constraint_name', None) == ACTIVE_BINDING_CONSTRAINT_NAME:
        return True
    if str(orig) == SQLITE_ACTIVE_BINDING_SIGNATURE:
        return True
    return False


def normalize_storage_scope(storage_scope: str | None, default: str = 'project') -> str:
    value = normalize_resolved_storage_scope(storage_scope)
    return value or default


def get_media_asset_kind(storage_scope: str | None) -> str:
    normalized_scope = normalize_storage_scope(storage_scope)
    if normalized_scope in DECLARED_STORAGE_SCOPES:
        return 'declared'
    if normalized_scope in LINKED_STORAGE_SCOPES:
        return 'linked'
    if normalized_scope in GENERATED_STORAGE_SCOPES:
        return 'generated'
    return 'runtime'


def get_media_asset_flags(storage_scope: str | None) -> dict:
    kind = get_media_asset_kind(storage_scope)
    return {
        'kind': kind,
        'is_runtime': kind == 'runtime',
        'is_declared': kind == 'declared',
        'is_linked': kind == 'linked',
        'is_generated': kind == 'generated',
    }


def is_generated_media_scope(storage_scope: str | None) -> bool:
    return get_media_asset_kind(storage_scope) == 'generated'


def _require_nondurable_scope(storage_scope: str | None, *, default: str) -> str:
    normalized_scope = normalize_storage_scope(storage_scope, default=default)
    if is_generated_media_scope(normalized_scope):
        raise HTTPException(status_code=400, detail='Generated artifact scopes are virtual-only and cannot be persisted as media assets')
    return normalized_scope


def media_asset_matches_filters(asset: MediaAsset, *, scope: str | None = None, kind: str | None = None) -> bool:
    normalized_scope = normalize_storage_scope(asset.storage_scope)
    normalized_filter_scope = normalize_storage_scope(scope, default='') if scope is not None else None
    normalized_kind = str(kind or '').strip().lower() or None
    if normalized_filter_scope is not None and normalized_scope != normalized_filter_scope:
        return False
    if normalized_kind is not None and get_media_asset_kind(normalized_scope) != normalized_kind:
        return False
    return True


def attach_canonical_media_identity(metadata: dict, *, media_asset_id: str | None = None, shot_version_id: str | None = None) -> dict:
    merged = dict(metadata or {})

    resolved_media_asset_id = media_asset_id or merged.get('horizons_media_asset_id') or merged.get('media_asset_id')
    resolved_shot_version_id = shot_version_id or merged.get('horizons_shot_version_id') or merged.get('version_id')
    if resolved_media_asset_id is not None:
        merged['media_asset_id'] = resolved_media_asset_id
        merged['horizons_media_asset_id'] = resolved_media_asset_id
    if resolved_shot_version_id is not None:
        merged['version_id'] = resolved_shot_version_id
        merged['horizons_shot_version_id'] = resolved_shot_version_id

    path = str(merged.get('path') or merged.get('file_path') or '').strip()
    if resolved_shot_version_id:
        merged['media_entity_type'] = 'shot_version'
        merged['media_entity_id'] = resolved_shot_version_id
        merged['media_entity_key'] = f'version:{resolved_shot_version_id}'
    elif resolved_media_asset_id:
        merged['media_entity_type'] = 'media_asset'
        merged['media_entity_id'] = resolved_media_asset_id
        merged['media_entity_key'] = f'asset:{resolved_media_asset_id}'
    elif path:
        merged['media_entity_type'] = 'path'
        merged['media_entity_id'] = path
        merged['media_entity_key'] = f'path:{path}'

    return merged


def serialize_media_asset(asset: MediaAsset) -> dict:
    normalized_scope = normalize_storage_scope(asset.storage_scope)
    return attach_canonical_media_identity({
        'id': asset.id,
        'project_id': asset.project_id,
        'file_path': asset.file_path,
        'path': asset.file_path,
        'storage_scope': normalized_scope,
        'content_hash': asset.content_hash,
        'file_size': asset.file_size,
        'modified_at': asset.modified_at,
        'source_signature': asset.source_signature,
        'unavailable_at': asset.unavailable_at,
        'unavailable_reason': asset.unavailable_reason,
        'exists': asset.unavailable_at is None,
        'created_at': asset.created_at,
        'updated_at': asset.updated_at,
        **get_media_asset_flags(normalized_scope),
    }, media_asset_id=asset.id)


def merge_storage_scope_metadata(metadata: dict, storage_scope: str | None, *, media_asset_id: str | None = None, exists: bool | None = None, shot_version_id: str | None = None) -> dict:
    normalized_scope = normalize_storage_scope(storage_scope)
    merged = {
        **metadata,
        'storage_scope': normalized_scope,
        **get_media_asset_flags(normalized_scope),
    }
    if exists is not None:
        merged['exists'] = exists
    return attach_canonical_media_identity(merged, media_asset_id=media_asset_id, shot_version_id=shot_version_id)


def merge_media_asset_metadata(metadata: dict, asset: MediaAsset, *, exists: bool | None = None, shot_version_id: str | None = None) -> dict:
    resolved_exists = asset.unavailable_at is None if exists is None else exists
    merged = merge_storage_scope_metadata(metadata, asset.storage_scope, media_asset_id=asset.id, exists=resolved_exists, shot_version_id=shot_version_id)
    if asset.unavailable_at is not None:
        merged['unavailable_at'] = asset.unavailable_at
        merged['unavailable_reason'] = asset.unavailable_reason or 'unavailable'
    return merged


def _content_hash_for_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None


def content_fingerprint(path: Path) -> str | None:
    """Return a bounded-cost fingerprint suitable for media identity checks.

    Full-file hashing makes registering large camera originals block on reading
    the entire source. This fingerprint instead hashes evenly spaced samples
    plus their offsets and the exact file size. It reads at most 4 MiB while
    still making same-name/same-size replacement collisions vanishingly
    unlikely in normal media workflows.
    """
    try:
        size = path.stat().st_size
        digest = hashlib.sha256()
        digest.update(f'{SOURCE_FINGERPRINT_ALGORITHM}:{size}'.encode('ascii'))
        if size <= SOURCE_FINGERPRINT_BYTES:
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
        else:
            sample_size = SOURCE_FINGERPRINT_BYTES // SOURCE_FINGERPRINT_SAMPLES
            max_offset = size - sample_size
            with path.open('rb') as handle:
                for index in range(SOURCE_FINGERPRINT_SAMPLES):
                    offset = (max_offset * index) // (SOURCE_FINGERPRINT_SAMPLES - 1)
                    handle.seek(offset)
                    sample = handle.read(sample_size)
                    if len(sample) != sample_size:
                        return None
                    digest.update(offset.to_bytes(8, 'big', signed=False))
                    digest.update(sample)
        return f'{SOURCE_FINGERPRINT_ALGORITHM}:{size}:{digest.hexdigest()}'
    except (OSError, ValueError):
        return None


def file_matches_content_identity(path: Path, expected: str | None) -> bool:
    """Compare a file with a stored runtime fingerprint or full SHA-256."""
    normalized = str(expected or '').strip().lower()
    if not normalized:
        return False
    if normalized.startswith(f'{SOURCE_FINGERPRINT_ALGORITHM}:'):
        return content_fingerprint(path) == normalized
    if len(normalized) == 64 and all(char in '0123456789abcdef' for char in normalized):
        return _content_hash_for_file(path) == normalized
    return False


def _asset_owner(project_id: str | None, storage_scope: str) -> str:
    normalized_project_id = str(project_id or '').strip()
    if storage_scope == 'media_root' and not normalized_project_id:
        return GLOBAL_MEDIA_PROJECT_ID
    if not normalized_project_id:
        raise ValueError('project_id is required for project media')
    return normalized_project_id


def _purge_asset_cache(db: Session, asset: MediaAsset) -> None:
    from app.services.media_resolution import (
        delivery_poster_cache_path_for_identity,
        generated_thumbnail_cache_path_for_identity,
        media_source_cache_identity,
    )
    from app.services.transcode_lifecycle import (
        all_transcode_identities_for_source,
        purge_transcode_identity,
    )

    cache_identities = [f'asset:{asset.id}']
    if asset.artifact_identity:
        active_shared_artifact = (
            db.query(MediaAsset.id)
            .filter(MediaAsset.id != asset.id)
            .filter(MediaAsset.artifact_identity == asset.artifact_identity)
            .filter(MediaAsset.unavailable_at.is_(None))
            .first()
            is not None
        )
        if not active_shared_artifact:
            cache_identities.append(asset.artifact_identity)
    if asset.source_signature:
        cache_identities.append(f'asset:{asset.id}:source:{asset.source_signature}')
    if asset.storage_scope == 'media_root' and asset.source_signature:
        active_shared_reference = (
            db.query(MediaAsset.id)
            .filter(MediaAsset.id != asset.id)
            .filter(MediaAsset.storage_scope == 'media_root')
            .filter(MediaAsset.source_signature == asset.source_signature)
            .filter(MediaAsset.unavailable_at.is_(None))
            .first()
            is not None
        )
        if not active_shared_reference:
            cache_identities.append(media_source_cache_identity(asset.source_signature))

    for cache_identity in cache_identities:
        for path in (
            generated_thumbnail_cache_path_for_identity(cache_identity),
            delivery_poster_cache_path_for_identity(cache_identity),
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    transcode_identities = {identity for cache_identity in cache_identities for identity in all_transcode_identities_for_source(cache_identity)}
    for identity in transcode_identities:
        purge_transcode_identity(identity, db=db)
    db.query(MediaMetadata).filter(MediaMetadata.cache_identity.in_(cache_identities)).delete(synchronize_session=False)


def _active_assets_for_binding(db: Session, *, project_id: str, storage_scope: str, file_path: str) -> list[MediaAsset]:
    assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.storage_scope == storage_scope)
        .filter(MediaAsset.file_path == file_path)
        .filter(MediaAsset.unavailable_at.is_(None))
        .order_by(MediaAsset.updated_at.desc(), MediaAsset.created_at.desc(), MediaAsset.id.asc())
        .with_for_update()
        .all()
    )
    return _sort_assets_for_active_binding(db, assets)


def _media_asset_reference_score(db: Session, asset_id: str) -> int:
    return (
        db.query(ShareLink).filter(ShareLink.media_asset_id == asset_id).filter(ShareLink.is_active.isnot(False)).count() * 100
        + db.query(HorizonShot).filter(HorizonShot.latest_media_asset_id == asset_id).count() * 80
        + db.query(HorizonShotVersion).filter(HorizonShotVersion.media_asset_id == asset_id).count() * 60
        + db.query(Comment).filter(Comment.horizons_media_asset_id == asset_id).count() * 20
        + db.query(ShotRegistryEntry).filter(ShotRegistryEntry.latest_media_asset_id == asset_id).count() * 20
        + db.query(VersionRegistryEntry).filter(VersionRegistryEntry.media_asset_id == asset_id).count() * 20
        + db.query(MediaMetadata).filter(MediaMetadata.media_asset_id == asset_id).count()
    )


def _sort_assets_for_active_binding(db: Session, assets: list[MediaAsset]) -> list[MediaAsset]:
    if len(assets) < 2:
        return assets

    score_by_id = {asset.id: _media_asset_reference_score(db, asset.id) for asset in assets}
    return sorted(
        assets,
        key=lambda asset: (
            -score_by_id.get(asset.id, 0),
            0 if asset.source_signature else 1,
            -(asset.updated_at or 0),
            -(asset.created_at or 0),
            asset.id or '',
        ),
    )


def retire_media_asset(db: Session, asset: MediaAsset, reason: str) -> None:
    if asset.unavailable_at is not None:
        return
    asset.unavailable_at = time.time()
    asset.unavailable_reason = reason
    asset.updated_at = asset.unavailable_at
    _purge_asset_cache(db, asset)
    db.add(asset)


def cleanup_retired_media_asset(db: Session, asset: MediaAsset) -> None:
    if asset.unavailable_at is None:
        return
    _purge_asset_cache(db, asset)


def _commit_and_cleanup(db: Session, retired_assets: list[MediaAsset]) -> None:
    for asset in retired_assets:
        cleanup_retired_media_asset(db, asset)
    db.commit()


def validate_media_asset_source(db: Session, asset: MediaAsset, full_path: Path | None) -> bool:
    external_project = (
        db.query(HorizonProject)
        .filter(HorizonProject.id == asset.project_id)
        .filter(HorizonProject.storage_root != 'data')
        .first()
    )
    if asset.unavailable_at is not None:
        if external_project and full_path and full_path.exists() and full_path.is_file():
            stat = full_path.stat()
            current_signature = source_signature(full_path)
            if file_matches_content_identity(full_path, asset.content_hash):
                asset.source_signature = current_signature
                asset.file_size = stat.st_size
                asset.modified_at = stat.st_mtime
                asset.unavailable_at = None
                asset.unavailable_reason = None
                asset.updated_at = time.time()
                db.add(asset)
                db.commit()
                return True
        return False
    if not full_path or not full_path.exists() or not full_path.is_file():
        retire_media_asset(db, asset, 'external_missing' if external_project else 'deleted')
        _commit_and_cleanup(db, [asset])
        return False
    current_signature = source_signature(full_path)
    if not asset.source_signature:
        asset.source_signature = current_signature
        asset.file_size = full_path.stat().st_size
        asset.modified_at = full_path.stat().st_mtime
        asset.content_hash = asset.content_hash or content_fingerprint(full_path)
        asset.updated_at = time.time()
        db.add(asset)
        db.commit()
        return True
    if asset.source_signature != current_signature:
        if file_matches_content_identity(full_path, asset.content_hash):
            stat = full_path.stat()
            asset.source_signature = current_signature
            asset.file_size = stat.st_size
            asset.modified_at = stat.st_mtime
            asset.updated_at = time.time()
            db.add(asset)
            db.commit()
            return True
        retire_media_asset(db, asset, 'external_signature_mismatch' if external_project else 'replaced')
        _commit_and_cleanup(db, [asset])
        return False
    if not asset.content_hash:
        asset.content_hash = content_fingerprint(full_path)
        asset.updated_at = time.time()
        db.add(asset)
        db.commit()
    return True


def retire_duplicate_active_media_assets(db: Session, *, project_id: str | None = None) -> int:
    query = db.query(
        MediaAsset.project_id,
        MediaAsset.storage_scope,
        MediaAsset.file_path,
        func.count(MediaAsset.id).label('active_count'),
    ).filter(MediaAsset.unavailable_at.is_(None))
    if project_id is not None:
        query = query.filter(MediaAsset.project_id == project_id)
    duplicates = (
        query.group_by(MediaAsset.project_id, MediaAsset.storage_scope, MediaAsset.file_path)
        .having(func.count(MediaAsset.id) > 1)
        .all()
    )
    retired = 0
    now = time.time()
    for duplicate in duplicates:
        assets = (
            db.query(MediaAsset)
            .filter(MediaAsset.project_id == duplicate.project_id)
            .filter(MediaAsset.storage_scope == duplicate.storage_scope)
            .filter(MediaAsset.file_path == duplicate.file_path)
            .filter(MediaAsset.unavailable_at.is_(None))
            .order_by(MediaAsset.updated_at.desc(), MediaAsset.created_at.desc(), MediaAsset.id.asc())
            .all()
        )
        assets = _sort_assets_for_active_binding(db, assets)
        for asset in assets[1:]:
            asset.unavailable_at = now
            asset.unavailable_reason = 'duplicate_active_generation'
            asset.updated_at = now
            db.add(asset)
            retired += 1
    if retired:
        db.commit()
    return retired


def register_media_asset(
    db: Session,
    project_id: str | None,
    file_path: str,
    storage_scope: str = 'project',
    *,
    commit: bool = True,
) -> MediaAsset | None:
    normalized_file_path = (file_path or '').strip().strip('/')
    if not normalized_file_path:
        return None

    requested_scope = _require_nondurable_scope(storage_scope, default='project')
    full_path, _job_key, resolved_scope = resolve_media_target(normalized_file_path, project_id, storage_scope=requested_scope, db=db)
    if not full_path or not full_path.exists() or not full_path.is_file():
        return None

    stat = full_path.stat()
    now = time.time()
    effective_scope = _require_nondurable_scope(resolved_scope or requested_scope, default='project')
    owner_id = _asset_owner(project_id, effective_scope)
    current_signature = source_signature(full_path)
    current_fingerprint: str | None = None

    def get_current_fingerprint() -> str | None:
        nonlocal current_fingerprint
        if current_fingerprint is None:
            current_fingerprint = content_fingerprint(full_path)
        return current_fingerprint

    def upsert_once() -> tuple[MediaAsset, list[MediaAsset]]:
        retired_assets: list[MediaAsset] = []
        active_assets = _active_assets_for_binding(db, project_id=owner_id, storage_scope=effective_scope, file_path=normalized_file_path)
        asset = active_assets[0] if active_assets else None
        for duplicate in active_assets[1:]:
            retire_media_asset(db, duplicate, 'duplicate_active_generation')
            retired_assets.append(duplicate)

        if asset is not None and not asset.source_signature:
            asset.source_signature = current_signature
            asset.content_hash = asset.content_hash or get_current_fingerprint()
        elif asset is not None and asset.source_signature != current_signature:
            if file_matches_content_identity(full_path, asset.content_hash):
                asset.source_signature = current_signature
            else:
                retire_media_asset(db, asset, 'replaced')
                retired_assets.append(asset)
                asset = None
        elif asset is not None and not asset.content_hash:
            asset.content_hash = get_current_fingerprint()

        if asset is None:
            asset_id = str(uuid.uuid4())
            asset = MediaAsset(
                id=asset_id,
                project_id=owner_id,
                file_path=normalized_file_path,
                storage_scope=effective_scope,
                content_hash=get_current_fingerprint(),
                file_size=stat.st_size,
                modified_at=stat.st_mtime,
                source_signature=current_signature,
                artifact_identity=(
                    media_source_cache_identity(current_signature)
                    if effective_scope == 'media_root'
                    else f'asset:{asset_id}'
                ),
                created_at=now,
                updated_at=now,
            )
        else:
            asset.file_path = normalized_file_path
            asset.storage_scope = effective_scope
            asset.file_size = stat.st_size
            asset.modified_at = stat.st_mtime
            asset.source_signature = current_signature
            asset.unavailable_at = None
            asset.unavailable_reason = None
            asset.updated_at = now
        db.add(asset)
        return asset, retired_assets

    last_error: IntegrityError | None = None
    for attempt in range(UNIQUE_BINDING_RETRY_LIMIT):
        try:
            if commit:
                asset, retired_assets = upsert_once()
                _commit_and_cleanup(db, retired_assets)
                db.refresh(asset)
                return asset
            with db.begin_nested():
                asset, _retired_assets = upsert_once()
                db.flush()
            return asset
        except IntegrityError as exc:
            last_error = exc
            if commit:
                db.rollback()
            if not _is_active_binding_integrity_error(exc):
                raise
            active_assets = _active_assets_for_binding(db, project_id=owner_id, storage_scope=effective_scope, file_path=normalized_file_path)
            if active_assets:
                return active_assets[0]
            if attempt == UNIQUE_BINDING_RETRY_LIMIT - 1:
                break
    raise last_error or RuntimeError('Failed to register media asset')


def resolve_media_asset_cache_target(
    db: Session,
    project_id: str,
    file_path: str,
    *,
    storage_scope: str = 'project',
    register_if_missing: bool = True,
) -> tuple[Path | None, str | None, MediaAsset | None]:
    from app.services.media_resolution import resolve_media_asset_path

    lookup_project_id = None if normalize_storage_scope(storage_scope) == 'media_root' else project_id
    asset = get_media_asset_by_path(db, lookup_project_id, file_path, storage_scope=storage_scope)
    if asset is None and register_if_missing:
        asset = register_media_asset(db, lookup_project_id, file_path, storage_scope=storage_scope)
    if asset is None:
        return None, None, None

    full_path, cache_key, _resolved_scope = resolve_media_asset_path(asset, project_id=lookup_project_id, db=db)
    if not full_path or not full_path.exists() or not cache_key:
        return None, None, asset
    return full_path, cache_key, asset


def list_media_assets(db: Session, project_id: str, *, scope: str | None = None, kind: str | None = None) -> list[MediaAsset]:
    assets = db.query(MediaAsset).filter(MediaAsset.project_id == project_id).order_by(MediaAsset.created_at.asc()).all()
    if scope is None and kind is None:
        return assets
    return [asset for asset in assets if media_asset_matches_filters(asset, scope=scope, kind=kind)]


def declare_media_asset(
    db: Session,
    project_id: str,
    file_path: str,
    *,
    storage_scope: str = 'horizons_declared',
    content_hash: str | None = None,
    file_size: int | None = None,
    modified_at: float | None = None,
) -> MediaAsset:
    normalized_path = (file_path or '').strip().strip('/')
    if not normalized_path:
        raise ValueError('file_path is required')

    normalized_scope = _require_nondurable_scope(storage_scope, default='horizons_declared')
    now = time.time()
    signature_parts = [
        'declared',
        normalized_scope,
        content_hash or '',
        str(file_size) if file_size is not None else '',
        str(modified_at) if modified_at is not None else '',
    ]
    declared_signature = ':'.join(signature_parts)

    def upsert_once() -> tuple[MediaAsset, list[MediaAsset]]:
        retired_assets: list[MediaAsset] = []
        active_assets = _active_assets_for_binding(db, project_id=project_id, storage_scope=normalized_scope, file_path=normalized_path)
        asset = active_assets[0] if active_assets else None
        for duplicate in active_assets[1:]:
            retire_media_asset(db, duplicate, 'duplicate_active_generation')
            retired_assets.append(duplicate)
        if asset is not None and asset.source_signature != declared_signature:
            retire_media_asset(db, asset, 'replaced')
            retired_assets.append(asset)
            asset = None

        if asset is None:
            asset_id = str(uuid.uuid4())
            asset = MediaAsset(
                id=asset_id,
                project_id=project_id,
                file_path=normalized_path,
                storage_scope=normalized_scope,
                content_hash=content_hash,
                file_size=file_size,
                modified_at=modified_at,
                source_signature=declared_signature,
                artifact_identity=f'asset:{asset_id}',
                created_at=now,
                updated_at=now,
            )
        else:
            asset.updated_at = now
        db.add(asset)
        return asset, retired_assets

    last_error: IntegrityError | None = None
    for attempt in range(UNIQUE_BINDING_RETRY_LIMIT):
        try:
            asset, retired_assets = upsert_once()
            _commit_and_cleanup(db, retired_assets)
            db.refresh(asset)
            return asset
        except IntegrityError as exc:
            last_error = exc
            db.rollback()
            if not _is_active_binding_integrity_error(exc):
                raise
            active_assets = _active_assets_for_binding(db, project_id=project_id, storage_scope=normalized_scope, file_path=normalized_path)
            if active_assets:
                return active_assets[0]
            if attempt == UNIQUE_BINDING_RETRY_LIMIT - 1:
                break
    raise last_error or RuntimeError('Failed to declare media asset')


def _normalize_asset_path(file_path: str | None) -> str:
    return str(file_path or '').strip().strip('/')


def get_media_asset_by_path(
    db: Session,
    project_id: str | None,
    file_path: str,
    *,
    storage_scope: str | None = None,
    include_unavailable: bool = False,
) -> MediaAsset | None:
    normalized_path = _normalize_asset_path(file_path)
    if not normalized_path:
        return None
    query = db.query(MediaAsset).filter(MediaAsset.file_path == normalized_path)
    if storage_scope:
        normalized_scope = normalize_storage_scope(storage_scope)
        query = query.filter(MediaAsset.storage_scope == normalized_scope)
        query = query.filter(MediaAsset.project_id == _asset_owner(project_id, normalized_scope))
    else:
        query = query.filter(MediaAsset.project_id == project_id)
    if not include_unavailable:
        query = query.filter(MediaAsset.unavailable_at.is_(None))
    return query.order_by(MediaAsset.updated_at.desc()).first()


def get_media_assets_under_prefix(db: Session, project_id: str, prefix: str) -> list[MediaAsset]:
    return get_media_assets_under_prefix_for_scope(db, project_id, prefix, storage_scope='project')


def get_media_assets_under_prefix_for_scope(db: Session, project_id: str, prefix: str, *, storage_scope: str) -> list[MediaAsset]:
    normalized_prefix = _normalize_asset_path(prefix)
    if not normalized_prefix:
        return []
    normalized_scope = normalize_storage_scope(storage_scope)
    owner_id = _asset_owner(project_id, normalized_scope)
    like_prefix = f'{escape_like_path(normalized_prefix)}/%'
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == owner_id)
        .filter(MediaAsset.storage_scope == normalized_scope)
        .filter(MediaAsset.unavailable_at.is_(None))
        .filter(or_(MediaAsset.file_path == normalized_prefix, MediaAsset.file_path.like(like_prefix, escape='\\')))
        .order_by(MediaAsset.created_at.asc())
        .all()
    )


def update_media_asset_path(
    db: Session,
    project_id: str,
    source_path: str,
    destination_path: str,
    *,
    storage_scope: str | None = None,
    file_size: int | None = None,
    modified_at: float | None = None,
    content_hash: str | None = None,
    commit: bool = True,
) -> MediaAsset | None:
    normalized_source = _normalize_asset_path(source_path)
    normalized_destination = _normalize_asset_path(destination_path)
    if not normalized_source or not normalized_destination:
        raise HTTPException(status_code=400, detail='Asset path is required')

    asset = get_media_asset_by_path(db, project_id, normalized_source, storage_scope=storage_scope or 'project')
    if asset is None:
        return None

    destination_asset = get_media_asset_by_path(db, project_id, normalized_destination, storage_scope=storage_scope or asset.storage_scope)
    if destination_asset and destination_asset.id != asset.id:
        raise HTTPException(status_code=400, detail='Media asset already exists at destination path')

    asset.file_path = normalized_destination
    if storage_scope:
        asset.storage_scope = normalize_storage_scope(storage_scope)
    resolved_path, _cache_key, _resolved_scope = resolve_media_target(asset.file_path, project_id, asset.storage_scope, db=db)
    if resolved_path and resolved_path.is_file():
        stat = resolved_path.stat()
        asset.source_signature = source_signature(resolved_path)
        asset.file_size = stat.st_size
        asset.modified_at = stat.st_mtime
    if file_size is not None:
        asset.file_size = file_size
    if modified_at is not None:
        asset.modified_at = modified_at
    if content_hash is not None:
        asset.content_hash = content_hash
    asset.updated_at = time.time()
    db.add(asset)
    if commit:
        db.commit()
        db.refresh(asset)
    else:
        db.flush()
    return asset


def update_media_assets_under_prefix(
    db: Session,
    project_id: str,
    source_prefix: str,
    destination_prefix: str,
    *,
    storage_scope: str | None = None,
    commit: bool = True,
) -> list[MediaAsset]:
    normalized_source = _normalize_asset_path(source_prefix)
    normalized_destination = _normalize_asset_path(destination_prefix)
    if not normalized_source or not normalized_destination:
        raise HTTPException(status_code=400, detail='Asset prefix is required')

    effective_scope = normalize_storage_scope(storage_scope or 'project')
    owner_id = _asset_owner(project_id, effective_scope)
    assets = get_media_assets_under_prefix_for_scope(db, project_id, normalized_source, storage_scope=effective_scope)
    if not assets:
        return []

    moving_ids = {asset.id for asset in assets}
    mapped_paths: dict[str, str] = {}
    for asset in assets:
        suffix = asset.file_path[len(normalized_source):].lstrip('/') if asset.file_path != normalized_source else ''
        next_path = '/'.join(part for part in [normalized_destination, suffix] if part)
        mapped_paths[asset.id] = next_path

    if len(set(mapped_paths.values())) != len(mapped_paths):
        raise HTTPException(status_code=400, detail='Media asset path collision during folder move')

    colliding_assets = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == owner_id)
        .filter(MediaAsset.storage_scope == effective_scope)
        .filter(MediaAsset.unavailable_at.is_(None))
        .filter(MediaAsset.file_path.in_(list(mapped_paths.values())))
        .all()
    )
    for colliding_asset in colliding_assets:
        if colliding_asset.id not in moving_ids:
            raise HTTPException(status_code=400, detail='Media asset already exists at destination path')

    now = time.time()
    for asset in assets:
        asset.file_path = mapped_paths[asset.id]
        if storage_scope:
            asset.storage_scope = normalize_storage_scope(storage_scope)
        resolved_path, _cache_key, _resolved_scope = resolve_media_target(asset.file_path, project_id, asset.storage_scope, db=db)
        if resolved_path and resolved_path.is_file():
            stat = resolved_path.stat()
            asset.source_signature = source_signature(resolved_path)
            asset.file_size = stat.st_size
            asset.modified_at = stat.st_mtime
        asset.updated_at = now
        db.add(asset)
    if commit:
        db.commit()
        for asset in assets:
            db.refresh(asset)
    else:
        db.flush()
    return assets


def delete_media_assets_under_path(
    db: Session,
    project_id: str,
    file_path: str,
    *,
    recursive: bool = False,
    storage_scopes: set[str] | None = None,
    commit: bool = True,
) -> list[str]:
    normalized_path = _normalize_asset_path(file_path)
    if not normalized_path:
        raise HTTPException(status_code=400, detail='Asset path is required')

    query = db.query(MediaAsset).filter(MediaAsset.project_id == project_id)
    if recursive:
        like_prefix = f'{escape_like_path(normalized_path)}/%'
        query = query.filter(or_(MediaAsset.file_path == normalized_path, MediaAsset.file_path.like(like_prefix, escape='\\')))
    else:
        query = query.filter(MediaAsset.file_path == normalized_path)

    normalized_scopes = None
    if storage_scopes is not None:
        normalized_scopes = {normalize_storage_scope(scope) for scope in storage_scopes if normalize_storage_scope(scope)}
        if normalized_scopes:
            query = query.filter(MediaAsset.storage_scope.in_(sorted(normalized_scopes)))

    assets = query.all()
    removed_ids = [asset.id for asset in assets]
    if not assets:
        return removed_ids

    for asset in assets:
        retire_media_asset(db, asset, 'deleted')
    if commit:
        _commit_and_cleanup(db, assets)
    else:
        db.flush()
    return removed_ids


def backfill_tracker_media_asset_ids(db: Session, project_id: str, tracker_name: str) -> dict:
    updated_versions = 0
    scanned_versions = 0

    with get_tracker_write_lock(project_id, tracker_name):
        tracker = load_tracker(project_id, tracker_name)
        changed = False
        for shot in tracker.get('shots', []) or []:
            for version in shot.get('versions', []) or []:
                file_path = (version or {}).get('file_path')
                if not file_path:
                    continue
                scanned_versions += 1
                asset = register_media_asset(db, project_id, file_path, storage_scope='tracker_version')
                if asset and not version.get('media_asset_id'):
                    version['media_asset_id'] = asset.id
                    updated_versions += 1
                    changed = True
        if changed:
            save_tracker(project_id, tracker_name, tracker, compute_stats=False)

    return {'scanned_versions': scanned_versions, 'updated_versions': updated_versions}
