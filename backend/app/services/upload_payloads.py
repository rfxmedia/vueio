import base64
import binascii
from io import BytesIO
from pathlib import Path
from typing import Collection

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_DIMENSION = 16_384
MAX_IMAGE_PIXELS = 32_000_000


async def read_bounded_upload(
    file: UploadFile,
    *,
    max_bytes: int,
    empty_detail: str = 'Upload was empty',
    too_large_detail: str = 'Upload is too large',
) -> bytes:
    """Read a small multipart upload without ever buffering beyond its limit."""
    contents = await file.read(max_bytes + 1)
    if len(contents) > max_bytes:
        raise HTTPException(status_code=413, detail=too_large_detail)
    if not contents:
        raise HTTPException(status_code=400, detail=empty_detail)
    return contents


def require_valid_image(
    contents: bytes,
    *,
    detail: str = 'Upload must be a valid image',
    allowed_formats: Collection[str] | None = None,
) -> None:
    try:
        with Image.open(BytesIO(contents)) as image:
            _validate_open_image(image, detail=detail, allowed_formats=allowed_formats)
    except HTTPException:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail=detail) from exc


def require_valid_image_path(
    path: str | Path,
    *,
    detail: str = 'Upload must be a valid image',
    allowed_formats: Collection[str] | None = None,
) -> None:
    try:
        with Image.open(path) as image:
            _validate_open_image(image, detail=detail, allowed_formats=allowed_formats)
    except HTTPException:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail=detail) from exc


def _validate_open_image(
    image: Image.Image,
    *,
    detail: str,
    allowed_formats: Collection[str] | None,
) -> None:
    width, height = image.size
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
        or (allowed_formats and image.format not in allowed_formats)
    ):
        raise HTTPException(status_code=400, detail=detail)
    image.verify()


def validate_png_data_url(
    value: str | None,
    *,
    max_bytes: int,
    too_large_detail: str = 'Payload is too large',
    invalid_detail: str = 'Payload must be a valid PNG image',
) -> bytes | None:
    if not value:
        return None
    if len(value.encode('utf-8')) > max_bytes:
        raise HTTPException(status_code=413, detail=too_large_detail)
    prefix = 'data:image/png;base64,'
    if not value.startswith(prefix):
        raise HTTPException(status_code=400, detail=invalid_detail)
    try:
        contents = base64.b64decode(value[len(prefix):], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=invalid_detail) from exc
    require_valid_image(contents, detail=invalid_detail, allowed_formats={'PNG'})
    return contents
