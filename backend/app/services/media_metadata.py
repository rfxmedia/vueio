from __future__ import annotations

import json
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import MediaMetadata
from app.services import media as media_service
from app.services.media_resolution import get_media_cache_identity


def _path_state(path: Path) -> tuple[int, float]:
    stat = path.stat()
    return int(stat.st_size), float(stat.st_mtime)


def _is_current(row: MediaMetadata, *, file_size: int, modified_at: float) -> bool:
    return int(row.file_size or 0) == file_size and abs(float(row.modified_at or 0) - modified_at) < 0.001


def _read_info(row: MediaMetadata) -> dict | None:
    try:
        data = json.loads(row.info_json or '{}')
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_info_with_session(
    db: Session,
    identity: str,
    info: dict,
    *,
    media_asset_id: str | None,
    path_str: str,
    file_size: int,
    modified_at: float,
) -> None:
    now = time.time()
    table = MediaMetadata.__table__
    values = {
        'cache_identity': identity,
        'media_asset_id': media_asset_id,
        'file_path': path_str,
        'file_size': file_size,
        'modified_at': modified_at,
        'info_json': json.dumps(info),
        'created_at': now,
        'updated_at': now,
    }
    update_values = {key: values[key] for key in ('media_asset_id', 'file_path', 'file_size', 'modified_at', 'info_json', 'updated_at')}
    dialect_name = db.get_bind().dialect.name
    if dialect_name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(table).values(**values).on_conflict_do_update(
            index_elements=[table.c.cache_identity],
            set_=update_values,
        )
        db.execute(stmt)
        return
    if dialect_name == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert

        stmt = insert(table).values(**values).on_conflict_do_update(
            index_elements=[table.c.cache_identity],
            set_=update_values,
        )
        db.execute(stmt)
        return

    row = db.query(MediaMetadata).filter(MediaMetadata.cache_identity == identity).first()
    if not row:
        row = MediaMetadata(cache_identity=identity, created_at=now)
    for key, value in values.items():
        if key != 'cache_identity':
            setattr(row, key, value)
    db.add(row)


def _write_info(
    db: Session | None,
    identity: str,
    info: dict,
    *,
    media_asset_id: str | None,
    path_str: str,
    file_size: int,
    modified_at: float,
) -> None:
    if db is not None and (db.in_transaction() or db.new or db.dirty or db.deleted):
        _write_info_with_session(
            db,
            identity,
            info,
            media_asset_id=media_asset_id,
            path_str=path_str,
            file_size=file_size,
            modified_at=modified_at,
        )
        return

    from app.db import SessionLocal

    cache_db = SessionLocal()
    try:
        _write_info_with_session(
            cache_db,
            identity,
            info,
            media_asset_id=media_asset_id,
            path_str=path_str,
            file_size=file_size,
            modified_at=modified_at,
        )
        cache_db.commit()
    finally:
        cache_db.close()


def video_metadata_cache_identity(
    file_path: Path,
    path_str: str,
    *,
    project_id: str | None = None,
    storage_scope: str | None = None,
    media_asset_id: str | None = None,
    cache_identity: str | None = None,
) -> str:
    if cache_identity:
        return cache_identity
    return get_media_cache_identity(
        project_id,
        path_str,
        file_path,
        storage_scope=storage_scope,
        asset_id=media_asset_id,
    )


def get_cached_video_info(
    db: Session | None,
    file_path: Path,
    path_str: str,
    *,
    project_id: str | None = None,
    storage_scope: str | None = None,
    media_asset_id: str | None = None,
    cache_identity: str | None = None,
) -> dict:
    if not media_service.is_video(file_path):
        return {}

    identity = video_metadata_cache_identity(
        file_path,
        path_str,
        project_id=project_id,
        storage_scope=storage_scope,
        media_asset_id=media_asset_id,
        cache_identity=cache_identity,
    )
    file_size, modified_at = _path_state(file_path)

    if db is not None:
        row = db.query(MediaMetadata).filter(MediaMetadata.cache_identity == identity).first()
        if row and _is_current(row, file_size=file_size, modified_at=modified_at):
            cached = _read_info(row)
            if cached is not None:
                return cached

    info = media_service.get_video_info(file_path)
    if db is not None:
        _write_info(
            db,
            identity,
            info,
            media_asset_id=media_asset_id,
            path_str=path_str,
            file_size=file_size,
            modified_at=modified_at,
        )
    return info
