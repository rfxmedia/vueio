from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from fractions import Fraction
from functools import lru_cache
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
from app.services.media import get_file_hash, is_image, is_video, probe_duration_seconds
from app.services.media_resolution import resolve_media_asset_path

settings = get_settings()
# v3: video frames show the frame the review player shows at that moment.
COMMENT_VISUAL_CACHE_VERSION = 'comment-visual-v3'


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

    asset, full_path, cache_identity = resolve_project_media(db, comment.project_id, asset_id)
    return {
        'comment': comment,
        'version': version,
        'shot': shot,
        'asset': asset,
        'full_path': full_path,
        'cache_identity': cache_identity or f'asset:{asset.id}',
    }


def resolve_project_media(db: Session, project_id: str, asset_id: str) -> tuple[MediaAsset, Path, str | None]:
    """Return the asset, file path and cache identity of project media. Check access first."""
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .filter(MediaAsset.id == asset_id)
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail='Media asset not found')
    full_path, cache_identity, _storage_scope = resolve_media_asset_path(asset, project_id=project_id, db=db)
    if not full_path or not full_path.exists():
        raise HTTPException(status_code=404, detail='Media file not found')
    return asset, full_path, cache_identity


def can_generate_comment_frame(path: Path) -> bool:
    from app.services.media import MODEL_EXTENSIONS
    return path.suffix.lower() not in MODEL_EXTENSIONS and (_is_image(path) or bool(shutil.which('ffmpeg')))


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff'}


@lru_cache(maxsize=128)
def _probe_video(path: str, _mtime_ns: int, _size: int) -> tuple[Fraction | None, float, tuple[int, int] | None]:
    # The file generation is part of the cache key, so a replaced file is probed again.
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
            'stream=r_frame_rate,avg_frame_rate,width,height,sample_aspect_ratio,duration:stream_side_data=rotation:format=duration',
            '-of', 'json', path,
        ], capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout or '{}')
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, 0.0, None
    stream = (data.get('streams') or [{}])[0]
    rate = None
    # The review player counts frames with r_frame_rate, as the file details do.
    for key in ('r_frame_rate', 'avg_frame_rate'):
        try:
            value = Fraction(str(stream.get(key) or ''))
        except (ValueError, ZeroDivisionError):
            continue
        if 1 <= value <= 240:
            rate = value
            break
    size = None
    try:
        aspect = str(stream.get('sample_aspect_ratio') or '1:1')
        sar = Fraction(aspect.replace(':', '/')) if aspect not in ('N/A', '0:1') else Fraction(1)
        width, height = round(int(stream['width']) * sar), int(stream['height'])
        rotation = next((item['rotation'] for item in stream.get('side_data_list', []) if 'rotation' in item), 0)
        if abs(round(rotation)) % 180 == 90:
            width, height = height, width
        if width > 0 and height > 0:
            size = (width, height)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    return rate, probe_duration_seconds(data), size


def _video_probe(source: Path) -> tuple[Fraction | None, float, tuple[int, int] | None]:
    """Return the frame rate, duration and display size of a video, as far as known."""
    try:
        stat = source.stat()
    except OSError:
        return None, 0.0, None
    return _probe_video(str(source), stat.st_mtime_ns, stat.st_size)


def frame_timestamp(source: Path, frame: int) -> float:
    """Return the time in seconds of a frame number, counted from 0. Images have one frame."""
    if is_image(source):
        return 0.0
    rate = _video_probe(source)[0] if is_video(source) else None
    if rate is None:
        raise HTTPException(status_code=422, detail='Frame numbers need a video with a known frame rate. Use a time in seconds.')
    # A quarter frame in, so the review player and the server agree on the frame.
    return float((frame + Fraction(1, 4)) / rate)


def media_display_size(source: Path) -> tuple[int, int]:
    """Return the width and height of media as the review player shows it."""
    if is_image(source):
        try:
            with Image.open(source) as image:
                width, height = image.size
                # Browsers apply the EXIF orientation of photos.
                if image.getexif().get(0x0112) in (5, 6, 7, 8):
                    width, height = height, width
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass  # Formats such as EXR are read by ffprobe below.
    size = _video_probe(source)[2]
    if size is None:
        raise HTTPException(status_code=422, detail='The size of this media is unknown.')
    return size


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


def _render_frame(source: Path, timestamp: float, output: Path, annotation_path: Path | None = None) -> None:
    if _is_image(source):
        _image_frame(source, output, annotation_path)
    else:
        width, height = _dimensions(annotation_path) if annotation_path else (960, -2)
        scale = f'scale={width}:-2' if height == -2 else (
            f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
            f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2'
        )
        seek = max(0.0, float(timestamp or 0))
        rate = _video_probe(source)[0]
        if rate is not None:
            # ffmpeg starts at the first frame at or after the seek time, but the
            # review player shows the frame that started at or before it.
            shown = math.floor(seek * rate + Fraction(1, 1000))
            seek = max(0.0, float((shown - Fraction(1, 4)) / rate))
        try:
            result = subprocess.run(
                ['ffmpeg', '-y', '-ss', f'{seek:.6f}',
                 '-i', str(source), '-frames:v', '1', '-vf', scale, '-q:v', '2', str(output)],
                capture_output=True,
                timeout=45,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail='Unable to generate the frame') from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail='ffmpeg is not available') from exc
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail='Unable to generate the frame')
    if not output.exists() or output.stat().st_size <= 0:
        raise HTTPException(status_code=500, detail='Unable to generate the frame')


def generate_comment_frame(ctx: dict, annotation_path: Path | None = None) -> Path:
    output = _cache_path(ctx, 'frame')
    if output.exists() and output.stat().st_size > 0:
        return output
    from app.services.media import MODEL_EXTENSIONS
    if ctx['full_path'].suffix.lower() in MODEL_EXTENSIONS:
        raise HTTPException(422, 'Open the saved 3D view in the review player.')
    _render_frame(ctx['full_path'], ctx['comment'].timestamp or 0, output, annotation_path)
    return output


def render_media_frame(source: Path, timestamp: float) -> bytes:
    """Return one frame of a video, or an image, as a JPEG 960 pixels wide.

    Frames are not cached: callers may ask for any moment.
    """
    from app.services.media import MODEL_EXTENSIONS
    if source.suffix.lower() in MODEL_EXTENSIONS:
        raise HTTPException(422, '3D models have no frames.')
    if not _is_image(source):
        duration = _video_probe(source)[1]
        if duration > 0:
            # A moment past the end shows the last frame.
            timestamp = min(timestamp, max(0.0, duration - 0.1))
    with tempfile.TemporaryDirectory(prefix='vueio-frame-') as directory:
        output = Path(directory) / 'frame.jpg'
        _render_frame(source, timestamp, output)
        return output.read_bytes()


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
