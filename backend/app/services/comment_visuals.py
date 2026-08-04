from __future__ import annotations

import base64
import binascii
import hashlib
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException
from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Comment, HorizonShot, HorizonShotVersion, MediaAsset
from app.services.horizons_fresh import (
    can_access_horizon_media_asset_id,
    can_access_horizon_shot_version_id,
    require_horizon_project_access,
)
from app.services.media import get_file_hash
from app.services.media_resolution import resolve_media_asset_path

settings = get_settings()
COMMENT_VISUAL_CACHE_VERSION = 'comment-visual-v2'


def comment_visual_url(comment_id: int, kind: str) -> str:
    return f'/api/comments/{comment_id}/{kind}'


def _cache_dir() -> Path:
    path = settings.thumbnail_dir / 'comment-visuals'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _decode_annotation_png(annotation_data: str | None) -> bytes | None:
    raw = (annotation_data or '').strip()
    if not raw:
        return None
    if raw.startswith('data:'):
        header, separator, raw = raw.partition(',')
        if not separator or 'base64' not in header.lower():
            raise HTTPException(status_code=400, detail='Unsupported annotation format')
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail='Invalid annotation data') from exc
    if not decoded.startswith(b'\x89PNG\r\n\x1a\n'):
        raise HTTPException(status_code=400, detail='Annotation is not a PNG image')
    return decoded


def write_annotation_png(comment: Comment) -> Path:
    annotation = _decode_annotation_png(comment.annotation_data)
    if not annotation:
        raise HTTPException(status_code=404, detail='Comment has no annotation')
    digest = hashlib.sha256(annotation).hexdigest()[:16]
    output = _cache_dir() / f'{comment.id}-{digest}-annotation.png'
    if not output.exists() or output.stat().st_size != len(annotation):
        output.write_bytes(annotation)
    return output


def build_comment_visual_context(db: Session, comment_id: int, user: dict, auth_mode: str) -> dict:
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment is None or not comment.project_id:
        raise HTTPException(status_code=404, detail='Comment not found')
    _project, access_role = require_horizon_project_access(
        db, comment.project_id, user, auth_mode=auth_mode, required_role='viewer'
    )

    version = None
    shot = None
    asset_id = comment.horizons_media_asset_id
    if comment.horizons_shot_version_id:
        if not can_access_horizon_shot_version_id(
            db,
            comment.project_id,
            comment.horizons_shot_version_id,
            user=user,
            access_role=access_role,
        ):
            raise HTTPException(status_code=404, detail='Comment not found')
        version = (
            db.query(HorizonShotVersion)
            .filter(HorizonShotVersion.project_id == comment.project_id)
            .filter(HorizonShotVersion.id == comment.horizons_shot_version_id)
            .first()
        )
        if version is None:
            raise HTTPException(status_code=404, detail='Shot version not found')
        asset_id = version.media_asset_id or asset_id
        shot = (
            db.query(HorizonShot)
            .filter(HorizonShot.project_id == comment.project_id)
            .filter(HorizonShot.id == version.shot_id)
            .first()
        )
    elif asset_id and not can_access_horizon_media_asset_id(
        db, comment.project_id, asset_id, user=user, access_role=access_role
    ):
        raise HTTPException(status_code=404, detail='Comment not found')
    if not asset_id:
        raise HTTPException(status_code=404, detail='Visual context requires a media target')

    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == comment.project_id)
        .filter(MediaAsset.id == asset_id)
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail='Media asset not found')
    full_path, cache_identity, _storage_scope = resolve_media_asset_path(
        asset, project_id=comment.project_id, db=db
    )
    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail='Media file not found')
    return {
        'comment': comment,
        'version': version,
        'shot': shot,
        'asset': asset,
        'full_path': full_path,
        'cache_identity': cache_identity or f'asset:{asset.id}',
    }


def can_generate_comment_frame(path: Path) -> bool:
    return _is_image(path) or bool(shutil.which('ffmpeg'))


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff'}


def _dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception as exc:
        raise HTTPException(status_code=500, detail='Unable to inspect annotation image') from exc
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=500, detail='Invalid annotation image dimensions')
    return width, height


def _cache_path(ctx: dict, kind: str) -> Path:
    comment = ctx['comment']
    full_path = ctx['full_path']
    try:
        media_mtime = int(full_path.stat().st_mtime)
    except OSError:
        media_mtime = 0
    key = ':'.join((
        COMMENT_VISUAL_CACHE_VERSION,
        kind,
        str(comment.id),
        str(comment.timestamp or 0),
        str(ctx.get('cache_identity') or ''),
        str(media_mtime),
        hashlib.sha256((comment.annotation_data or '').encode()).hexdigest()[:16],
    ))
    return _cache_dir() / f'{get_file_hash(key)}.jpg'


def _image_frame(source: Path, output: Path, annotation: Path | None) -> None:
    width, height = _dimensions(annotation) if annotation else (960, -1)
    try:
        with Image.open(source) as image:
            source_image = image.convert('RGB')
            if height <= 0:
                height = max(1, round(source_image.height * width / max(1, source_image.width)))
            canvas = Image.new('RGB', (width, height), (0, 0, 0))
            source_image.thumbnail((width, height), Image.Resampling.LANCZOS)
            canvas.paste(source_image, ((width - source_image.width) // 2, (height - source_image.height) // 2))
            canvas.save(output, format='JPEG', quality=92)
    except Exception as exc:
        raise HTTPException(status_code=500, detail='Unable to generate comment frame') from exc


def generate_comment_frame(ctx: dict, annotation_path: Path | None = None) -> Path:
    output = _cache_path(ctx, 'frame')
    if output.exists() and output.stat().st_size > 0:
        return output
    source = ctx['full_path']
    if _is_image(source):
        _image_frame(source, output, annotation_path)
    else:
        width, height = _dimensions(annotation_path) if annotation_path else (960, -2)
        scale = f'scale={width}:-2' if height == -2 else (
            f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
            f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2'
        )
        try:
            result = subprocess.run(
                ['ffmpeg', '-y', '-ss', f"{max(0.0, float(ctx['comment'].timestamp or 0)):.6f}",
                 '-i', str(source), '-frames:v', '1', '-vf', scale, '-q:v', '2', str(output)],
                capture_output=True,
                timeout=45,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail='Unable to generate comment frame') from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail='ffmpeg is not available') from exc
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail='Unable to generate comment frame')
    if not output.exists() or output.stat().st_size <= 0:
        raise HTTPException(status_code=500, detail='Unable to generate comment frame')
    return output


def generate_annotated_comment_frame(ctx: dict) -> Path:
    annotation_path = write_annotation_png(ctx['comment'])
    frame_path = generate_comment_frame(ctx, annotation_path)
    output = _cache_path(ctx, 'annotated-frame')
    if output.exists() and output.stat().st_size > 0:
        return output
    try:
        with Image.open(frame_path).convert('RGB') as frame:
            with Image.open(annotation_path).convert('RGBA') as annotation:
                if annotation.size != frame.size:
                    annotation = annotation.resize(frame.size, Image.Resampling.LANCZOS)
                composite = frame.convert('RGBA')
                composite.alpha_composite(annotation)
                composite.convert('RGB').save(output, format='JPEG', quality=92)
    except Exception as exc:
        raise HTTPException(status_code=500, detail='Unable to generate annotated comment frame') from exc
    return output
