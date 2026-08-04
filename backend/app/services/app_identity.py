from __future__ import annotations

import mimetypes
import shutil
import time
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppIdentity
from app.services.external_urls import normalize_external_http_url
from app.services.media import IMAGE_EXTENSIONS
from app.services.naming import safe_name_part
from app.services.upload_payloads import read_bounded_upload

settings = get_settings()

DEFAULT_TEAM_NAME = 'Vue'
TEAM_LOGO_PREFIX = 'team-logo-'
MAX_TEAM_LOGO_BYTES = 2 * 1024 * 1024
LOGO_CONTENT_TYPE_EXTENSIONS = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/tiff': '.tiff',
    'image/heic': '.heic',
    'image/heif': '.heif',
}


def normalize_team_name(value: str | None) -> str:
    return str(value or '').strip()[:120] or DEFAULT_TEAM_NAME


def normalize_website_url(value: str | None) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    candidate = normalize_external_http_url(raw)
    if not candidate:
        raise HTTPException(status_code=400, detail='Website must be a valid http or https URL')
    return candidate


def normalize_team_logo_upload_name(value: str | None) -> str:
    name = Path(str(value or '').strip()).name
    if not name or not name.startswith(TEAM_LOGO_PREFIX):
        return ''
    if Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
        return ''
    return name


def team_logo_upload_path(upload_name: str) -> Path:
    name = normalize_team_logo_upload_name(upload_name)
    if not name:
        raise HTTPException(status_code=404, detail='No team logo')
    return settings.thumbnail_dir / 'team-logos' / name


def build_team_logo_upload_name(original_filename: str | None) -> str:
    suffix = Path(original_filename or 'logo.png').suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = '.png'
    stem = safe_name_part(Path(original_filename or 'logo').stem, 'logo')[:40]
    return f'{TEAM_LOGO_PREFIX}{stem}-{uuid.uuid4().hex[:12]}{suffix}'


def get_app_identity_record(db: Session) -> AppIdentity:
    record = db.query(AppIdentity).filter(AppIdentity.id == 1).first()
    if record:
        return record
    now = time.time()
    record = AppIdentity(id=1, team_name=DEFAULT_TEAM_NAME, website_url='', logo_upload_name='', created_at=now, updated_at=now)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def serialize_app_identity(record: AppIdentity) -> dict:
    logo_name = normalize_team_logo_upload_name(record.logo_upload_name)
    return {
        'team_name': normalize_team_name(record.team_name),
        'website_url': normalize_external_http_url(record.website_url),
        'logo_upload_name': logo_name,
        'logo_url': f'/api/identity/logo?v={logo_name}' if logo_name else '',
    }


def save_app_identity(db: Session, *, team_name: str | None = None, website_url: str | None = None, updated_by: str | None = None) -> AppIdentity:
    record = get_app_identity_record(db)
    if team_name is not None:
        record.team_name = normalize_team_name(team_name)
    if website_url is not None:
        record.website_url = normalize_website_url(website_url)
    record.updated_by = updated_by
    record.updated_at = time.time()
    db.commit()
    db.refresh(record)
    return record


async def store_team_logo_upload(file: UploadFile) -> str:
    filename = file.filename or 'logo.png'
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        mapped_ext = LOGO_CONTENT_TYPE_EXTENSIONS.get(str(file.content_type or '').lower())
        if not mapped_ext:
            raise HTTPException(status_code=400, detail='Upload must be an image')
        filename = f'logo{mapped_ext}'

    contents = await read_bounded_upload(
        file,
        max_bytes=MAX_TEAM_LOGO_BYTES,
        too_large_detail='Logo image is too large',
    )

    upload_name = build_team_logo_upload_name(filename)
    upload_path = team_logo_upload_path(upload_name)
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    with open(upload_path, 'wb') as handle:
        handle.write(contents)
    return upload_name


def store_team_logo_source(source_path: Path) -> str:
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail='Logo source file was not found')
    if source_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail='Choose an image file')

    upload_name = build_team_logo_upload_name(source_path.name)
    upload_path = team_logo_upload_path(upload_name)
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, upload_path)
    return upload_name


def set_team_logo(db: Session, upload_name: str, *, updated_by: str | None = None) -> AppIdentity:
    record = get_app_identity_record(db)
    previous = normalize_team_logo_upload_name(record.logo_upload_name)
    record.logo_upload_name = normalize_team_logo_upload_name(upload_name)
    record.updated_by = updated_by
    record.updated_at = time.time()
    db.commit()
    db.refresh(record)
    if previous and previous != record.logo_upload_name:
        delete_team_logo_upload(previous)
    return record


def clear_team_logo(db: Session, *, updated_by: str | None = None) -> AppIdentity:
    record = get_app_identity_record(db)
    previous = normalize_team_logo_upload_name(record.logo_upload_name)
    record.logo_upload_name = ''
    record.updated_by = updated_by
    record.updated_at = time.time()
    db.commit()
    db.refresh(record)
    delete_team_logo_upload(previous)
    return record


def delete_team_logo_upload(upload_name: str | None) -> None:
    name = normalize_team_logo_upload_name(upload_name)
    if not name:
        return
    try:
        team_logo_upload_path(name).unlink()
    except FileNotFoundError:
        pass


def build_team_logo_response(upload_name: str | None) -> FileResponse:
    name = normalize_team_logo_upload_name(upload_name)
    if not name:
        raise HTTPException(status_code=404, detail='No team logo')
    path = team_logo_upload_path(name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail='No team logo')
    media_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return FileResponse(path, media_type=media_type)
