from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import unquote

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import HorizonShotVersion, MediaAsset, ShareLink
from app.services.file_metadata import build_file_metadata
from app.services.media import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, format_size
from app.services.media_assets import attach_canonical_media_identity, merge_media_asset_metadata, merge_storage_scope_metadata, register_media_asset
from app.services.media_resolution import get_media_cache_identity, resolve_media_asset_path, resolve_media_target, resolve_project_content_target, resolve_project_link_target
from app.services.project_links import find_link_target, join_rel_path, linked_virtual_paths_for_source, link_storage_scope, merge_linked_path_metadata
from app.services.projects import get_project_dir, load_project, load_project_links
from app.services.uploads import UPLOAD_SCOPE_PROJECT, UPLOAD_SCOPE_SHARED, get_latest_upload_metadata

_NO_SHARE_REQUEST = object()
_request_share_access_token: ContextVar[str | None | object] = ContextVar(
    'vueio_request_share_access_token',
    default=_NO_SHARE_REQUEST,
)


def set_request_share_access_token(token: str | None) -> Token:
    return _request_share_access_token.set((token or '').strip() or None)


def reset_request_share_access_token(token: Token) -> None:
    _request_share_access_token.reset(token)


def _effective_share_access_token(explicit_token: str | None) -> str | None:
    request_token = _request_share_access_token.get()
    if request_token is _NO_SHARE_REQUEST:
        return explicit_token
    return request_token


def build_share_id() -> str:
    return secrets.token_urlsafe(24)


def build_unique_share_id(db: Session, *, attempts: int = 8) -> str:
    for _attempt in range(attempts):
        share_id = build_share_id()
        with db.no_autoflush:
            exists = db.query(ShareLink.id).filter(ShareLink.id == share_id).first()
        if not exists:
            return share_id
    raise HTTPException(status_code=503, detail='Could not create a unique share link')


def _is_share_id_unique_conflict(exc: IntegrityError) -> bool:
    orig = getattr(exc, 'orig', None)
    sqlstate = getattr(orig, 'pgcode', None) or getattr(orig, 'sqlstate', None)
    if sqlstate == '23505':
        diag = getattr(orig, 'diag', None)
        table_name = getattr(diag, 'table_name', None)
        constraint_name = getattr(diag, 'constraint_name', None)
        column_name = getattr(diag, 'column_name', None)
        return table_name == 'shares' and (constraint_name in {'shares_pkey', 'pk_shares'} or column_name == 'id')

    message = str(orig or exc)
    sqlite_unique_messages = {
        'UNIQUE constraint failed: shares.id',
        'PRIMARY KEY constraint failed: shares.id',
    }
    if message in sqlite_unique_messages:
        return True
    if 'Duplicate entry' in message and "for key 'PRIMARY'" in message:
        return True
    if 'Duplicate entry' in message and 'shares.PRIMARY' in message:
        return True
    return False


def _share_insert_values(share: ShareLink) -> dict:
    values = {}
    for column in ShareLink.__table__.columns:
        value = getattr(share, column.name)
        if value is None and column.default is not None:
            continue
        values[column.name] = value
    return values


def create_share_link_with_retry(db: Session, factory: Callable[[str], ShareLink], *, attempts: int = 4) -> ShareLink:
    for _attempt in range(attempts):
        share = factory(build_unique_share_id(db))
        connection = db.connection()
        nested = connection.begin_nested()
        try:
            connection.execute(ShareLink.__table__.insert().values(_share_insert_values(share)))
            nested.commit()
        except IntegrityError as exc:
            nested.rollback()
            if _is_share_id_unique_conflict(exc):
                continue
            raise
        with db.no_autoflush:
            persisted = db.get(ShareLink, share.id)
        if persisted is None:
            raise HTTPException(status_code=503, detail='Could not create a unique share link')
        return persisted
    raise HTTPException(status_code=503, detail='Could not create a unique share link')


def hash_share_password(password: str | None) -> str | None:
    if not password or not password.strip():
        return None
    salt = secrets.token_urlsafe(16)
    iterations = 210_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations).hex()
    return f'pbkdf2_sha256${iterations}${salt}${digest}'


def verify_share_password(password: str | None, password_hash: str | None) -> bool:
    if not password_hash:
        return True
    if not password:
        return False
    if password_hash.startswith('pbkdf2_sha256$'):
        try:
            _scheme, iterations_raw, salt, expected = password_hash.split('$', 3)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations_raw)).hex()
            if hmac.compare_digest(digest, expected):
                return True
        except Exception:
            pass
        try:
            _scheme, iterations_raw, salt_b64, expected_b64 = password_hash.split('$', 3)
            salt = base64.b64decode(salt_b64.encode())
            expected = base64.b64decode(expected_b64.encode())
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, int(iterations_raw))
            return hmac.compare_digest(digest, expected)
        except Exception:
            return False
    # Backward compatibility for existing protected shares.
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), password_hash)


SHARE_ACCESS_TOKEN_TTL_SECONDS = 60 * 60


def _share_token_secret() -> bytes:
    return get_settings().SECRET_KEY.encode()


def _share_token_password_fingerprint(share: ShareLink) -> str:
    return hashlib.sha256((share.password_hash or '').encode()).hexdigest()[:16]


def _share_token_signature(payload: str) -> str:
    return hmac.new(_share_token_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def issue_share_access_token(share: ShareLink, *, ttl_seconds: int = SHARE_ACCESS_TOKEN_TTL_SECONDS) -> str:
    expires_at = int(time.time() + max(60, ttl_seconds))
    payload = f'v1.{share.id}.share.{expires_at}.{_share_token_password_fingerprint(share)}'
    signature = _share_token_signature(payload)
    return f'{payload}.{signature}'


def verify_share_access_token(share: ShareLink, token: str | None) -> bool:
    if not token:
        return False
    parts = token.split('.')
    if len(parts) != 6:
        return False
    version, token_share_id, scope, expires_raw, password_fingerprint, signature = parts
    if version != 'v1' or scope != 'share' or token_share_id != share.id:
        return False
    try:
        expires_at = int(expires_raw)
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    if password_fingerprint != _share_token_password_fingerprint(share):
        return False
    payload = '.'.join(parts[:-1])
    return hmac.compare_digest(signature, _share_token_signature(payload))


@dataclass(frozen=True)
class CanonicalVirtualPath:
    parts: tuple[str, ...]

    @property
    def path(self) -> str:
        return '/'.join(self.parts)

    def contains(self, candidate: 'CanonicalVirtualPath') -> bool:
        if not self.parts:
            return True
        return candidate.parts[:len(self.parts)] == self.parts


def parse_virtual_path(raw_path: str | None, *, allow_empty: bool = False, field_name: str = 'path') -> CanonicalVirtualPath:
    value = str(raw_path or '').strip()
    if not value:
        if allow_empty:
            return CanonicalVirtualPath(())
        raise HTTPException(status_code=400, detail=f'{field_name} is required')
    if '\x00' in value or '\\' in value:
        raise HTTPException(status_code=400, detail=f'Invalid {field_name}')

    decoded = value
    for _attempt in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value

    if decoded.startswith('/') or decoded.startswith('//') or '\x00' in decoded or '\\' in decoded:
        raise HTTPException(status_code=400, detail=f'Invalid {field_name}')

    parts: list[str] = []
    for segment in decoded.split('/'):
        if not segment:
            continue
        if segment in {'.', '..'}:
            raise HTTPException(status_code=400, detail=f'Invalid {field_name}')
        parts.append(segment)
    if not parts and not allow_empty:
        raise HTTPException(status_code=400, detail=f'{field_name} is required')
    return CanonicalVirtualPath(tuple(parts))


def normalize_virtual_path(raw_path: str | None, *, allow_empty: bool = False, field_name: str = 'path') -> str:
    return parse_virtual_path(raw_path, allow_empty=allow_empty, field_name=field_name).path


def require_path_within_shared_root(root_path: str | None, candidate_path: str | None) -> str:
    try:
        root = parse_virtual_path(root_path, allow_empty=True, field_name='shared root')
        candidate = parse_virtual_path(candidate_path, allow_empty=not bool(root.parts), field_name='path')
    except HTTPException as exc:
        raise HTTPException(status_code=403, detail='Access denied - path outside shared folder') from exc
    if not root.contains(candidate):
        raise HTTPException(status_code=403, detail='Access denied - path outside shared folder')
    return candidate.path


def record_share_access(share: ShareLink, db: Session) -> None:
    now = time.time()
    db.execute(
        update(ShareLink)
        .where(ShareLink.id == share.id)
        .values(access_count=func.coalesce(ShareLink.access_count, 0) + 1, last_accessed=now)
        .execution_options(synchronize_session=False)
    )
    db.expire(share, ['access_count', 'last_accessed'])


def validate_share(
    share_id: str,
    password: str | None,
    db: Session,
    allowed_types: Iterable[str],
    *,
    share_token: str | None = None,
    track_access: bool = False,
    allow_file_request: bool = False,
    allow_password_auth: bool = False,
) -> ShareLink:
    share = db.query(ShareLink).filter(
        ShareLink.id == share_id,
        ShareLink.share_type.in_(list(allowed_types)),
    ).first()
    if not share:
        raise HTTPException(status_code=404, detail='Share not found')
    if not share.is_active:
        raise HTTPException(status_code=403, detail='This share link has been revoked')
    if share.expires_at and time.time() > share.expires_at:
        raise HTTPException(status_code=403, detail='This share link has expired')
    if share.password_hash:
        token_valid = (
            False
            if allow_password_auth
            else verify_share_access_token(share, _effective_share_access_token(share_token))
        )
        password_valid = bool(
            allow_password_auth
            and password
            and verify_share_password(password, share.password_hash)
        )
        if not token_valid and not password_valid:
            if allow_password_auth and password:
                raise HTTPException(status_code=401, detail='Invalid password')
            raise HTTPException(status_code=401, detail='Password required')
    if share.request_files and not allow_file_request:
        raise HTTPException(status_code=403, detail='This file request only accepts uploads')
    if share.project_id:
        from app.models import HorizonProject
        from app.services.horizons_fresh import is_deleted_horizon_project

        project = db.query(HorizonProject).filter(HorizonProject.id == share.project_id).first()
        if is_deleted_horizon_project(project):
            raise HTTPException(status_code=410, detail='The shared project was deleted')
    if share.share_type in {'file', 'project-file'} and not share.media_asset_id:
        raise HTTPException(
            status_code=410,
            detail='This legacy file share is no longer available; create a new share link',
        )
    if share.media_asset_id:
        asset = db.query(MediaAsset).filter(MediaAsset.id == share.media_asset_id).first()
        if not asset:
            raise HTTPException(status_code=410, detail='The shared file is unavailable')
        full_path, _cache_key, _scope = resolve_media_asset_path(asset, project_id=share.project_id, db=db)
        if not full_path:
            raise HTTPException(status_code=410, detail='The shared file was deleted or replaced')
    if track_access:
        record_share_access(share, db)
    return share


def _path_within_shared_root(root_path: str | None, candidate_path: str | None) -> bool:
    try:
        root = parse_virtual_path(root_path, allow_empty=True, field_name='shared root')
        candidate = parse_virtual_path(candidate_path, allow_empty=not bool(root.parts), field_name='path')
    except HTTPException:
        return False
    return root.contains(candidate)


def is_horizons_share_project(share: ShareLink) -> bool:
    if not share.project_id:
        return False
    return not (get_project_dir(share.project_id) / 'project.json').exists()


def _require_shared_horizon_project(share: ShareLink, db: Session | None):
    if not share.project_id or db is None or not is_horizons_share_project(share):
        return None
    from app.services.horizons_fresh import get_horizon_project

    return get_horizon_project(db, share.project_id)


def build_project_file_info_payload(project_id: str, requested_path: str, full_path: Path | None, *, db: Session | None = None, storage_scope: str | None = None, asset=None, exists: bool = True) -> dict:
    resolved_asset = asset
    unique_shot_version_id = None
    if resolved_asset is None and db is not None:
        from app.services.horizons_fresh import get_horizon_media_asset_by_path

        resolved_asset = get_horizon_media_asset_by_path(db, project_id, requested_path)

    if resolved_asset is not None and db is not None:
        from app.models import HorizonShotVersion

        version_ids = [
            version_id
            for version_id, in (
                db.query(HorizonShotVersion.id)
                .filter(HorizonShotVersion.project_id == project_id)
                .filter(HorizonShotVersion.media_asset_id == resolved_asset.id)
                .order_by(HorizonShotVersion.updated_at.desc(), HorizonShotVersion.created_at.desc(), HorizonShotVersion.id.asc())
                .all()
            )
        ]
        if len(version_ids) == 1:
            unique_shot_version_id = version_ids[0]

    if full_path and full_path.exists():
        metadata = build_file_metadata(
            full_path,
            requested_path,
            db=db,
            project_id=project_id,
            storage_scope=resolved_asset.storage_scope if resolved_asset else storage_scope,
            media_asset_id=resolved_asset.id if resolved_asset else None,
        )
        if resolved_asset:
            payload = merge_media_asset_metadata(metadata, resolved_asset, shot_version_id=unique_shot_version_id)
            if db is not None:
                payload.update(get_latest_upload_metadata(db, scope_type=UPLOAD_SCOPE_PROJECT, project_id=project_id, final_path=requested_path) or {})
            return payload

        match = find_link_target(load_project_links(project_id).get('links', []), requested_path)
        if match:
            link, suffix = match
            source_path = str(link.get('source_path') or '').strip()
            source_full_path = join_rel_path(source_path, suffix) if suffix else source_path
            linked_scope = link_storage_scope(link)
            linked_asset = (
                register_media_asset(db, project_id, source_full_path, storage_scope=linked_scope)
                if db is not None and linked_scope == 'project'
                else None
            )
            payload = attach_canonical_media_identity(
                merge_linked_path_metadata(
                    metadata,
                    source_path=source_full_path,
                    is_folder=full_path.is_dir(),
                    storage_scope=linked_scope,
                ),
                media_asset_id=linked_asset.id if linked_asset else None,
            )
            if db is not None:
                payload.update(get_latest_upload_metadata(db, scope_type=UPLOAD_SCOPE_PROJECT, project_id=project_id, final_path=requested_path) or {})
            return payload

        if storage_scope:
            payload = merge_storage_scope_metadata(metadata, storage_scope)
            if db is not None:
                payload.update(get_latest_upload_metadata(db, scope_type=UPLOAD_SCOPE_PROJECT, project_id=project_id, final_path=requested_path) or {})
            return payload

        payload = attach_canonical_media_identity(metadata)
        if db is not None:
            payload.update(get_latest_upload_metadata(db, scope_type=UPLOAD_SCOPE_PROJECT, project_id=project_id, final_path=requested_path) or {})
        return payload

    if resolved_asset:
        ext = Path(requested_path).suffix.lower()
        size = resolved_asset.file_size or 0
        payload = merge_media_asset_metadata({
            'name': Path(requested_path).name,
            'path': requested_path,
            'file_path': requested_path,
            'type': 'file',
            'extension': ext.lstrip('.'),
            'is_video': ext in VIDEO_EXTENSIONS,
            'is_image': ext in IMAGE_EXTENSIONS,
            'is_pdf': ext == '.pdf',
            'size': size,
            'size_formatted': format_size(size),
            'mtime': resolved_asset.modified_at or resolved_asset.updated_at or resolved_asset.created_at,
            'ctime': resolved_asset.created_at,
            'duration': 0,
            'duration_formatted': '',
            'needs_transcode': ext in VIDEO_EXTENSIONS,
        }, resolved_asset, exists=exists, shot_version_id=unique_shot_version_id)
        if db is not None:
            payload.update(get_latest_upload_metadata(db, scope_type=UPLOAD_SCOPE_PROJECT, project_id=project_id, final_path=requested_path) or {})
        return payload

    raise HTTPException(status_code=404, detail='File not found')


def build_shared_file_info_payload(share: ShareLink, path: str, db: Session, *, media_asset_id: str | None = None) -> dict:
    requested_path = normalize_virtual_path(path or share.path or '', allow_empty=True)
    resolved_asset_id = media_asset_id or share.media_asset_id
    bound_asset = db.query(MediaAsset).filter(MediaAsset.id == resolved_asset_id).first() if resolved_asset_id else None

    if share.project_id and requested_path and is_horizons_share_project(share):
        from app.services.horizons_fresh import get_horizon_media_asset_by_path

        asset = get_horizon_media_asset_by_path(db, share.project_id, requested_path)
        if asset is not None:
            raise HTTPException(status_code=409, detail='Horizons shared media objects must use explicit object routes')

    full_path, _cache_key = resolve_shared_media_target(share, requested_path, db=db, media_asset_id=media_asset_id)

    if share.project_id and requested_path:
        if bound_asset:
            full_path, _cache_key, storage_scope = resolve_media_asset_path(bound_asset, project_id=share.project_id, db=db)
            return build_project_file_info_payload(share.project_id, requested_path, full_path, db=db, storage_scope=storage_scope, asset=bound_asset, exists=bool(full_path))
        return build_project_file_info_payload(share.project_id, requested_path, full_path, db=db)

    if share.share_type in {'file', 'folder'}:
        if bound_asset:
            return merge_media_asset_metadata(build_file_metadata(full_path, requested_path, db=db), bound_asset)
        payload = merge_linked_path_metadata(build_file_metadata(full_path, requested_path, db=db), source_path=requested_path, is_folder=full_path.is_dir())
        payload.update(get_latest_upload_metadata(db, scope_type=UPLOAD_SCOPE_SHARED, final_path=requested_path) or {})
        return payload

    return build_file_metadata(full_path, requested_path, db=db)


def _resolve_horizons_media_target_by_refs(
    db: Session,
    project_id: str,
    *,
    horizons_media_asset_id: str | None = None,
    horizons_shot_version_id: str | None = None,
) -> tuple[Path | None, str | None, str | None, str | None, str | None]:
    if not horizons_media_asset_id and not horizons_shot_version_id:
        return None, None, None, None, None

    asset: MediaAsset | None = None
    version: HorizonShotVersion | None = None

    if horizons_shot_version_id:
        version = (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.id == horizons_shot_version_id)
            .filter(HorizonShotVersion.project_id == project_id)
            .first()
        )
        if version is None:
            raise HTTPException(status_code=404, detail='Horizons shot version not found')
        if not version.media_asset_id:
            raise HTTPException(status_code=409, detail='Horizons shot version is not linked to a media asset')
        asset = (
            db.query(MediaAsset)
            .filter(MediaAsset.id == version.media_asset_id)
            .filter(MediaAsset.project_id == project_id)
            .first()
        )
        if asset is None:
            raise HTTPException(status_code=404, detail='Horizons media asset not found')

    if horizons_media_asset_id:
        explicit_asset = (
            db.query(MediaAsset)
            .filter(MediaAsset.id == horizons_media_asset_id)
            .filter(MediaAsset.project_id == project_id)
            .first()
        )
        if explicit_asset is None:
            raise HTTPException(status_code=404, detail='Horizons media asset not found')
        if asset is not None and explicit_asset.id != asset.id:
            raise HTTPException(status_code=409, detail='Horizons media refs do not agree on the same asset')
        asset = explicit_asset

    if asset is None:
        return None, None, None, None, None

    full_path, cache_key, storage_scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
    return full_path, cache_key or f'asset:{asset.id}', storage_scope or getattr(asset, 'storage_scope', None) or 'project', asset.id, asset.file_path


def resolve_shared_horizons_object_target(
    share: ShareLink,
    db: Session,
    *,
    horizons_media_asset_id: str | None = None,
    horizons_shot_version_id: str | None = None,
) -> tuple[Path | None, str, str | None, str | None, str]:
    if not share.project_id or not is_horizons_share_project(share):
        raise HTTPException(status_code=404, detail='Horizons shared media object not found')

    full_path, cache_key, storage_scope, asset_id, canonical_path = _resolve_horizons_media_target_by_refs(
        db,
        share.project_id,
        horizons_media_asset_id=horizons_media_asset_id,
        horizons_shot_version_id=horizons_shot_version_id,
    )
    normalized_path = str(canonical_path or '').strip().strip('/')
    if not normalized_path or not asset_id:
        raise HTTPException(status_code=404, detail='Horizons shared media object not found')

    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == asset_id)
        .filter(MediaAsset.project_id == share.project_id)
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail='Horizons shared media object not found')
    shared_version = None
    asset_versions = []
    if share.share_type in {'project', 'project-folder', 'project-file', 'tracker', 'page'}:
        asset_versions = (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.project_id == share.project_id)
            .filter(HorizonShotVersion.media_asset_id == asset.id)
            .all()
        )
        from app.services.horizons.version_publication import version_is_published

        if horizons_shot_version_id:
            shared_version = next(
                (version for version in asset_versions if version.id == horizons_shot_version_id),
                None,
            )
        if horizons_shot_version_id and (
            shared_version is None or not version_is_published(shared_version)
        ):
            raise HTTPException(status_code=403, detail='This version is not published to shares')
        if not horizons_shot_version_id and asset_versions and not any(
            version_is_published(version) for version in asset_versions
        ):
            raise HTTPException(status_code=403, detail='This version is not published to shares')
    asset_virtual_paths = (
        linked_virtual_paths_for_source(load_project_links(share.project_id).get('links', []), asset.file_path)
        if asset and asset.storage_scope == 'media_root'
        else [normalized_path]
    )
    shared_path = normalize_virtual_path(share.path, allow_empty=True, field_name='shared root')
    if share.share_type in {'file', 'project-file'} and shared_path and shared_path not in asset_virtual_paths:
        raise HTTPException(status_code=403, detail='Access denied - can only access shared file')
    if share.share_type in {'folder', 'project-folder'} and shared_path and not any(
        _path_within_shared_root(shared_path, virtual_path) for virtual_path in asset_virtual_paths
    ):
        raise HTTPException(status_code=403, detail='Access denied - path outside shared folder')
    if share.share_type == 'tracker':
        if not horizons_shot_version_id:
            raise HTTPException(status_code=409, detail='Tracker shares require a horizons shot version id')
        from app.services.horizons_fresh import get_horizon_tracker_for_share

        shared_tracker = get_horizon_tracker_for_share(db, share)
        version = shared_version
        if version is None or version.tracker_id != shared_tracker.id:
            raise HTTPException(status_code=403, detail='This share does not grant access to the requested tracker media')
    if share.share_type == 'page':
        from app.services.horizon_pages import get_horizon_page_by_ref, page_allows_media_asset

        page = get_horizon_page_by_ref(db, share.project_id, share.page_id or '')
        version = shared_version
        if not page_allows_media_asset(db, page, asset, version):
            raise HTTPException(status_code=403, detail='This page does not grant access to the requested media')

    return full_path, cache_key or f'asset:{asset_id}', storage_scope, asset_id, normalized_path


def resolve_project_thumbnail_target(project_id: str, requested_path: str, *, db: Session | None = None, user: dict | None = None, access_role: str | None = None) -> tuple[Path | None, str | None, str | None, str | None]:
    is_legacy = (get_project_dir(project_id) / 'project.json').exists()
    if is_legacy:
        full_path, cache_key, storage_scope = resolve_project_link_target(project_id, requested_path)
        if full_path:
            return full_path, cache_key, storage_scope or 'media_root', None
        full_path, cache_key, _storage_scope = resolve_project_content_target(project_id, requested_path)
        return full_path, cache_key, 'project', None

    if db is None:
        return None, None, None, None

    from app.services.horizons_fresh import get_visible_horizon_media_asset_by_path, is_restricted_horizon_artist

    asset = get_visible_horizon_media_asset_by_path(db, project_id, requested_path, user=user, access_role=access_role)
    if asset:
        raise HTTPException(status_code=409, detail='Horizons media objects must use explicit object routes')

    # For non-asset files: fall back to link/filesystem resolution (admin/owner/editor only)
    restricted_view = is_restricted_horizon_artist(user, access_role)
    if restricted_view:
        return None, None, None, None
    full_path, cache_key, storage_scope = resolve_project_link_target(project_id, requested_path)
    if full_path:
        return full_path, cache_key, storage_scope or 'media_root', None
    full_path, cache_key, _storage_scope = resolve_project_content_target(project_id, requested_path)
    return full_path, cache_key, 'project', None


def resolve_shared_media_target(share: ShareLink, path: str, db: Session | None = None, *, media_asset_id: str | None = None) -> tuple[Path, str]:
    if share.share_type == 'tracker':
        raise HTTPException(status_code=409, detail='Tracker shares require explicit media object routes')

    raw_file_path = path or share.path or ''
    try:
        file_path = normalize_virtual_path(raw_file_path, allow_empty=True, field_name='path')
        shared_path = normalize_virtual_path(share.path, allow_empty=True, field_name='shared root')
    except HTTPException as exc:
        if share.share_type in ['folder', 'project-folder']:
            raise HTTPException(status_code=403, detail='Access denied - path outside shared folder') from exc
        raise
    if share.share_type in ['file', 'project-file'] and file_path and file_path != shared_path:
        raise HTTPException(status_code=403, detail='Access denied - can only access shared file')
    if share.share_type in ['folder', 'project-folder'] and shared_path:
        file_path = require_path_within_shared_root(shared_path, file_path)

    if not file_path:
        raise HTTPException(status_code=400, detail='No path provided')

    resolved_asset_id = media_asset_id or (share.media_asset_id if share.share_type in {'file', 'project-file'} else None)
    if resolved_asset_id and db is not None and share.share_type in {'file', 'folder'}:
        asset = db.query(MediaAsset).filter(MediaAsset.id == resolved_asset_id).first()
        normalized_path = str(file_path).strip().strip('/')
        if not asset or asset.project_id != '__media_root__' or asset.file_path != normalized_path:
            raise HTTPException(status_code=404, detail='Media asset not found')
        full_path, cache_key, _storage_scope = resolve_media_asset_path(asset, db=db)
        if not full_path:
            raise HTTPException(status_code=410, detail='The shared file was deleted or replaced')
        return full_path, cache_key or f'asset:{asset.id}'

    if share.share_type == 'page':
        if db is None:
            raise HTTPException(status_code=403, detail='Page share access requires scoped validation')
        from app.services.horizon_pages import get_horizon_page_by_ref, page_allows_path

        page = get_horizon_page_by_ref(db, share.project_id, share.page_id or '')
        if not page_allows_path(page, file_path):
            raise HTTPException(status_code=403, detail='This page does not grant access to the requested file')

    if share.share_type in ['file', 'folder']:
        full_path, transcode_key, storage_scope = resolve_media_target(file_path, storage_scope='media_root')
        if not full_path:
            raise HTTPException(status_code=404, detail='File not found')
        cache_key = get_media_cache_identity(None, file_path, full_path, storage_scope=storage_scope, resolved_job_key=transcode_key)
        return full_path, cache_key

    match = find_link_target(load_project_links(share.project_id).get('links', []), file_path)
    if match:
        link, suffix = match
        linked_source_path = str(link.get('source_path') or '').strip()
        if not linked_source_path:
            raise HTTPException(status_code=404, detail='File not found')
        target_path = join_rel_path(linked_source_path, suffix) if suffix else linked_source_path
        if db is not None and share.share_type in {'project', 'project-folder', 'project-file', 'page'}:
            from app.services.horizons_fresh import get_horizon_media_asset_by_path
            from app.services.horizons.version_publication import (
                held_media_asset_ids_for_project,
                held_media_paths_for_project,
            )

            linked_asset = get_horizon_media_asset_by_path(db, share.project_id, target_path)
            if (
                linked_asset is not None
                and str(linked_asset.id) in held_media_asset_ids_for_project(db, share.project_id)
            ):
                raise HTTPException(status_code=403, detail='This version is not published to shares')
        full_path, transcode_key, storage_scope = resolve_media_target(
            target_path,
            share.project_id,
            link_storage_scope(link),
            db=db,
        )
        if not full_path:
            raise HTTPException(status_code=404, detail='File not found')
        if (
            db is not None
            and share.share_type in {'project', 'project-folder', 'project-file', 'page'}
            and full_path.resolve(strict=False) in held_media_paths_for_project(db, share.project_id)
        ):
            raise HTTPException(status_code=403, detail='This version is not published to shares')
        cache_key = get_media_cache_identity(None, target_path, full_path, storage_scope=storage_scope, resolved_job_key=transcode_key)
        return full_path, cache_key

    if db is not None and is_horizons_share_project(share):
        from app.services.horizons_fresh import get_horizon_media_asset_by_path

        asset = get_horizon_media_asset_by_path(db, share.project_id, file_path)
        if asset:
            raise HTTPException(status_code=409, detail='Horizons shared media objects must use explicit object routes')

        full_path, transcode_key, resolved_scope = resolve_media_target(file_path, share.project_id, storage_scope='project')
        if not full_path or not full_path.exists():
            raise HTTPException(status_code=404, detail='File not found')
        cache_key = get_media_cache_identity(share.project_id, file_path, full_path, storage_scope=resolved_scope or 'project', resolved_job_key=transcode_key)
        return full_path, cache_key

    full_path, transcode_key, resolved_scope = resolve_media_target(file_path, share.project_id, storage_scope='project')
    if not full_path:
        raise HTTPException(status_code=404, detail='File not found')
    cache_key = get_media_cache_identity(share.project_id, file_path, full_path, storage_scope=resolved_scope or 'project', resolved_job_key=transcode_key)
    return full_path, cache_key


def get_shared_content_info_dict(share: ShareLink, db: Session | None = None) -> dict:
    if share.share_type in ['file', 'folder']:
        return {
            'share_type': share.share_type,
            'path': share.path,
            'is_folder': share.is_folder,
            'project_id': None,
            'project_title': None,
            'allow_download': share.allow_download,
            'allow_upload': share.allow_upload,
            'request_files': share.request_files,
            'tracker_name': None,
            'tracker_id': None,
            'project_source': None,
        }

    project_title = share.project_id
    project_thumbnail_path = None
    if is_horizons_share_project(share):
        project = _require_shared_horizon_project(share, db)
        if project is not None:
            project_title = project.title or share.project_id
            project_thumbnail_path = project.thumbnail_path
    else:
        project = load_project(share.project_id)
        project_title = project.get('title', 'Unknown')
        project_thumbnail_path = project.get('thumbnail_path')

    tracker_id = share.tracker_id
    tracker_name = share.tracker_name
    if db is not None and share.share_type == 'tracker':
        try:
            from app.services.horizons_fresh import get_horizon_tracker_for_share

            tracker = get_horizon_tracker_for_share(db, share)
            tracker_id = tracker.id
            tracker_name = tracker.name
        except HTTPException:
            pass

    payload = {
        'share_type': share.share_type,
        'path': share.path,
        'is_folder': share.is_folder,
        'project_id': share.project_id,
        'page_id': share.page_id,
        'project_title': project_title,
        'thumbnail_path': project_thumbnail_path,
        'allow_download': share.allow_download,
        'allow_upload': share.allow_upload,
        'request_files': share.request_files,
        'tracker_id': tracker_id,
        'tracker_name': tracker_name,
        'project_source': 'horizons_db' if share.project_id else None,
        'media_asset_id': share.media_asset_id,
    }

    if db is not None and share.project_id and not share.is_folder and is_horizons_share_project(share):
        try:
            from app.services.horizons_fresh import get_horizon_media_asset_by_path

            asset = get_horizon_media_asset_by_path(db, share.project_id, share.path or '')
            if asset is not None:
                full_path, _cache_key, storage_scope = resolve_media_asset_path(asset, project_id=share.project_id, db=db)
                info = build_project_file_info_payload(
                    share.project_id,
                    share.path or '',
                    full_path,
                    db=db,
                    storage_scope=storage_scope,
                    asset=asset,
                    exists=bool(full_path and full_path.exists()),
                )
                if info.get('media_asset_id'):
                    payload['media_asset_id'] = info.get('media_asset_id')
                if info.get('horizons_shot_version_id'):
                    payload['horizons_shot_version_id'] = info.get('horizons_shot_version_id')
        except HTTPException:
            pass

    return payload
