from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.media import IMAGE_EXTENSIONS
from app.services.naming import safe_name_part
from app.services.upload_payloads import read_bounded_upload

settings = get_settings()

DELIVERY_LOGO_PREFIX = 'delivery-logo-'
MAX_DELIVERY_LOGO_BYTES = 2 * 1024 * 1024
DELIVERY_LOGO_CONTENT_TYPE_EXTENSIONS = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/tiff': '.tiff',
    'image/heic': '.heic',
    'image/heif': '.heif',
}


def normalize_delivery_logo_upload_name(value: str | None) -> str:
    name = Path(str(value or '').strip()).name
    if not name or not name.startswith(DELIVERY_LOGO_PREFIX):
        return ''
    if Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
        return ''
    return name


def build_delivery_logo_upload_name(project_id: str, original_filename: str | None) -> str:
    suffix = Path(original_filename or 'logo.png').suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = '.png'
    project_part = safe_name_part(project_id, 'project')[:80]
    return f'{DELIVERY_LOGO_PREFIX}{project_part}-{uuid.uuid4().hex[:12]}{suffix}'


def delivery_logo_upload_path(upload_name: str) -> Path:
    name = normalize_delivery_logo_upload_name(upload_name)
    if not name:
        raise HTTPException(status_code=404, detail='No delivery logo')
    return settings.thumbnail_dir / 'delivery-logos' / name


async def store_delivery_logo_upload(project_id: str, file: UploadFile) -> str:
    filename = file.filename or 'logo.png'
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        mapped_ext = DELIVERY_LOGO_CONTENT_TYPE_EXTENSIONS.get(str(file.content_type or '').lower())
        if not mapped_ext:
            raise HTTPException(status_code=400, detail='Upload must be an image')
        filename = f'logo{mapped_ext}'

    contents = await read_bounded_upload(
        file,
        max_bytes=MAX_DELIVERY_LOGO_BYTES,
        too_large_detail='Logo image is too large',
    )

    upload_name = build_delivery_logo_upload_name(project_id, filename)
    upload_path = delivery_logo_upload_path(upload_name)
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    with open(upload_path, 'wb') as handle:
        handle.write(contents)
    return upload_name


def store_delivery_logo_source(project_id: str, source_path: Path) -> str:
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail='Logo source file was not found')
    if source_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail='Choose an image file')

    upload_name = build_delivery_logo_upload_name(project_id, source_path.name)
    upload_path = delivery_logo_upload_path(upload_name)
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, upload_path)
    return upload_name


def delete_delivery_logo_upload(upload_name: str | None) -> None:
    name = normalize_delivery_logo_upload_name(upload_name)
    if not name:
        return
    path = delivery_logo_upload_path(name)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def preserve_delivery_logo_upload(upload_name: str | None) -> None:
    name = normalize_delivery_logo_upload_name(upload_name)
    if not name:
        return
    try:
        path = delivery_logo_upload_path(name)
        if path.is_file():
            os.utime(path, None)
    except OSError:
        pass


def build_delivery_logo_response(upload_name: str | None) -> FileResponse:
    name = normalize_delivery_logo_upload_name(upload_name)
    if not name:
        raise HTTPException(status_code=404, detail='No delivery logo')
    path = delivery_logo_upload_path(name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail='No delivery logo')
    media_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    return FileResponse(path, media_type=media_type)
