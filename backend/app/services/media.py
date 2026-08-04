from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import threading
from pathlib import Path

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse

from app.config import get_settings
from app.runtime_state import executor

settings = get_settings()

THUMBNAIL_PLACEHOLDER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180"><rect width="320" height="180" fill="#101010"/><rect x="24" y="24" width="272" height="132" rx="8" fill="#1d1d1d" stroke="#2c2c2c"/><polygon points="138,80 138,100 158,90" fill="#6a6a6a"/><text x="160" y="126" text-anchor="middle" fill="#6a6a6a" font-family="Arial, sans-serif" font-size="12">Thumbnail queued</text></svg>"""
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif', '.heic', '.heif', '.exr', '.dpx'}
GENERATED_IMAGE_PREVIEW_EXTENSIONS = {'.exr', '.dpx'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.mxf', '.prores', '.r3d'}
AUDIO_EXTENSIONS = {'.weba', '.m4a', '.mp3', '.wav', '.ogg', '.opus'}
PDF_EXTENSIONS = {'.pdf'}
_thumbnail_jobs_in_progress: set[str] = set()
_thumbnail_jobs_lock = threading.Lock()


def get_file_hash(path: str) -> str:
    # Existing thumbnail/cache paths depend on this non-security identifier.
    return hashlib.md5(path.encode(), usedforsecurity=False).hexdigest()[:12]


def get_safe_path(path_str: str) -> Path:
    clean_path = path_str.lstrip('/')
    root = settings.MEDIA_ROOT.resolve()
    full_path = (root / clean_path).resolve()
    try:
        full_path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail='Access denied')
    return full_path


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def needs_transcode(path: Path) -> bool:
    return path.suffix.lower() not in {'.mp4', '.webm', '.m4v'}


def format_size(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'


def format_duration_label(seconds: float | int | None) -> str:
    try:
        total_seconds = max(0, int(float(seconds or 0)))
    except Exception:
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def get_folder_item_count(folder_path: Path) -> int:
    count = 0
    try:
        for entry in os.scandir(folder_path):
            if not entry.name.startswith('.') and entry.name not in settings.hidden_storage_folders:
                count += 1
    except Exception:
        pass
    return count


def probe_duration_seconds(data: dict) -> float:
    """Read duration from either the container or its streams."""
    def positive_seconds(value) -> float:
        try:
            duration = float(value)
            return duration if math.isfinite(duration) and duration > 0 else 0.0
        except (TypeError, ValueError):
            return 0.0

    container_duration = positive_seconds(data.get('format', {}).get('duration'))
    if container_duration:
        return container_duration

    stream_durations = []
    for stream in data.get('streams', []):
        stream_durations.append(positive_seconds(stream.get('duration')))
        try:
            numerator, denominator = str(stream.get('time_base') or '').split('/', 1)
            stream_duration = float(stream.get('duration_ts')) * float(numerator) / float(denominator)
            stream_durations.append(positive_seconds(stream_duration))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return max(stream_durations, default=0.0)


def get_video_duration_quick(path: Path) -> float:
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(path)
        ], capture_output=True, text=True, timeout=5)
        data = json.loads(result.stdout)
        return probe_duration_seconds(data)
    except Exception:
        return 0


def _clean_probe_value(value) -> str:
    text = str(value or '').strip()
    return '' if not text or text.upper() == 'N/A' else text


def _format_probe_codec(stream: dict) -> str:
    codec = _clean_probe_value(stream.get('codec_name')) or 'unknown'
    profile = _clean_probe_value(stream.get('profile'))
    if codec == 'prores':
        if '4444' in profile:
            return 'ProRes 4444'
        if 'HQ' in profile:
            return 'ProRes 422 HQ'
        if 'LT' in profile:
            return 'ProRes 422 LT'
        if 'Proxy' in profile:
            return 'ProRes 422 Proxy'
        if '422' in profile:
            return 'ProRes 422'
    return f'{codec} ({profile})' if profile else codec


def _format_bitrate(value) -> str:
    try:
        bitrate = int(float(value or 0))
    except Exception:
        return ''
    if bitrate <= 0:
        return ''
    if bitrate >= 1_000_000:
        return f'{bitrate / 1_000_000:.1f} Mbps'
    return f'{round(bitrate / 1000)} kbps'


def _format_audio_layout(stream: dict) -> str:
    layout = _clean_probe_value(stream.get('channel_layout'))
    channels = stream.get('channels')
    if layout:
        return layout
    try:
        channel_count = int(channels or 0)
    except Exception:
        channel_count = 0
    if channel_count == 1:
        return 'mono'
    if channel_count == 2:
        return 'stereo'
    return f'{channel_count} channels' if channel_count else ''


def _first_stream(streams: list[dict], codec_type: str) -> dict | None:
    return next((stream for stream in streams if stream.get('codec_type') == codec_type), None)


def get_video_info(path: Path) -> dict:
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(path)
        ], capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or not result.stdout.strip():
            return {'duration': 0, 'frames': 0, 'fps': 24, 'resolution': 'unknown', 'codec': 'unknown', 'valid': False}

        data = json.loads(result.stdout)
        if not data.get('format') or not data.get('streams'):
            return {'duration': 0, 'frames': 0, 'fps': 24, 'resolution': 'unknown', 'codec': 'unknown', 'valid': False}

        format_data = data.get('format', {})
        streams = data.get('streams', [])
        duration = probe_duration_seconds(data)
        frames, fps, width, height, codec = 0, 24, 0, 0, 'unknown'
        video_stream = _first_stream(streams, 'video')
        audio_stream = _first_stream(streams, 'audio')

        if video_stream:
            try:
                frames = int(video_stream.get('nb_frames', 0))
            except Exception:
                frames = 0
            width = int(video_stream.get('width', 0) or 0)
            height = int(video_stream.get('height', 0) or 0)
            codec = _format_probe_codec(video_stream)

            fps_str = video_stream.get('r_frame_rate') or video_stream.get('avg_frame_rate') or '24/1'
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) > 0 else 24
            if not frames and duration and fps:
                frames = int(round(duration * fps))

        bit_depth = ''
        if video_stream:
            bit_depth = (
                _clean_probe_value(video_stream.get('bits_per_raw_sample'))
                or _clean_probe_value(video_stream.get('bits_per_sample'))
            )

        audio_info = None
        if audio_stream:
            sample_rate = _clean_probe_value(audio_stream.get('sample_rate'))
            audio_bits = (
                _clean_probe_value(audio_stream.get('bits_per_sample'))
                or _clean_probe_value(audio_stream.get('bits_per_raw_sample'))
            )
            audio_info = {
                'codec': _format_probe_codec(audio_stream),
                'channels': audio_stream.get('channels') or None,
                'channel_layout': _format_audio_layout(audio_stream),
                'sample_rate': f'{round(int(sample_rate) / 1000, 1):g} kHz' if sample_rate.isdigit() else sample_rate,
                'bitrate': _format_bitrate(audio_stream.get('bit_rate')),
                'bit_depth': audio_bits,
            }

        return {
            'duration': duration,
            'frames': frames,
            'fps': round(fps, 2),
            'resolution': f'{width}x{height}',
            'codec': codec,
            'bit_depth': bit_depth,
            'pixel_format': _clean_probe_value(video_stream.get('pix_fmt')) if video_stream else '',
            'color_space': _clean_probe_value(video_stream.get('color_space')) if video_stream else '',
            'color_transfer': _clean_probe_value(video_stream.get('color_transfer')) if video_stream else '',
            'color_primaries': _clean_probe_value(video_stream.get('color_primaries')) if video_stream else '',
            'video_bitrate': _format_bitrate(video_stream.get('bit_rate')) if video_stream else '',
            'container_bitrate': _format_bitrate(format_data.get('bit_rate')),
            'audio': audio_info,
            'has_audio': bool(audio_info),
            'valid': True,
        }
    except Exception:
        return {'duration': 0, 'frames': 0, 'fps': 24, 'resolution': 'unknown', 'codec': 'unknown', 'valid': False}


THUMBNAIL_WIDTH = 960
DELIVERY_POSTER_WIDTH = 1920
THUMBNAIL_JPEG_QUALITY = 2


def thumbnail_video_filter(width: int) -> str:
    normalized_width = max(320, int(width or THUMBNAIL_WIDTH))
    return f'scale=ceil(iw*sar/2)*2:ih,setsar=1,scale={normalized_width}:-2'


def generate_thumbnail(media_path: Path, output_path: Path, *, width: int = THUMBNAIL_WIDTH) -> bool:
    try:
        info = get_video_info(media_path)
        seek_time = 0 if not info or not info.get('valid', False) or info.get('duration', 0) <= 0 else max(1, info['duration'] * 0.1)
        video_filter = thumbnail_video_filter(width)

        subprocess.run([
            'ffmpeg', '-y', '-ss', str(seek_time), '-i', str(media_path),
            '-vframes', '1', '-vf', video_filter, '-q:v', str(THUMBNAIL_JPEG_QUALITY), str(output_path)
        ], capture_output=True, timeout=30)

        if output_path.exists() and output_path.stat().st_size > 0:
            return True

        if output_path.exists():
            output_path.unlink()

        subprocess.run([
            'ffmpeg', '-y', '-i', str(media_path), '-vframes', '1', '-vf', video_filter, '-q:v', str(THUMBNAIL_JPEG_QUALITY), str(output_path)
        ], capture_output=True, timeout=30)

        if output_path.exists() and output_path.stat().st_size > 0:
            return True

        if output_path.exists():
            output_path.unlink()
        return False
    except Exception:
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass
        return False


def thumbnail_placeholder_response():
    return Response(
        content=THUMBNAIL_PLACEHOLDER_SVG,
        media_type='image/svg+xml',
        headers={'Cache-Control': 'no-store, max-age=0'},
    )


def build_thumbnail_response(
    full_path: Path,
    thumb_path: Path,
    *,
    missing_detail: str = 'Thumbnail not available',
    purge_empty_cache: bool = False,
    preferred_video_source: Path | None = None,
    queue_missing: bool = True,
    thumbnail_width: int = THUMBNAIL_WIDTH,
):
    generated_image_preview = full_path.suffix.lower() in GENERATED_IMAGE_PREVIEW_EXTENSIONS
    if is_image(full_path) and not generated_image_preview:
        return FileResponse(
            full_path,
            headers={'Cache-Control': 'private, max-age=3600'},
        )

    if thumb_path.exists():
        if thumb_path.stat().st_size > 0:
            return FileResponse(
                thumb_path,
                media_type='image/jpeg',
                headers={'Cache-Control': 'private, max-age=31536000, immutable'},
            )
        if purge_empty_cache:
            try:
                thumb_path.unlink()
            except Exception:
                pass

    if is_video(full_path) or generated_image_preview:
        if not queue_missing:
            return thumbnail_placeholder_response()
        thumbnail_source = preferred_video_source if preferred_video_source and preferred_video_source.exists() else full_path
        queue_thumbnail_generation(thumbnail_source, thumb_path, width=thumbnail_width)
        return thumbnail_placeholder_response()

    raise HTTPException(status_code=404, detail=missing_detail)


def queue_thumbnail_generation(media_path: Path, output_path: Path, *, width: int = THUMBNAIL_WIDTH):
    job_key = str(output_path)
    with _thumbnail_jobs_lock:
        if job_key in _thumbnail_jobs_in_progress:
            return
        _thumbnail_jobs_in_progress.add(job_key)

    def _worker():
        try:
            generate_thumbnail(media_path, output_path, width=width)
        finally:
            with _thumbnail_jobs_lock:
                _thumbnail_jobs_in_progress.discard(job_key)

    executor.submit(_worker)
