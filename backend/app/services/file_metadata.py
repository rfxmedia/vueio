from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.media import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, format_size
from app.services.media_metadata import get_cached_video_info

PDF_EXTENSIONS = {'.pdf'}


def build_file_metadata(
    file_path: Path,
    path_str: str,
    *,
    db=None,
    project_id: str | None = None,
    storage_scope: str | None = None,
    media_asset_id: str | None = None,
    cache_identity: str | None = None,
) -> dict:
    stat = file_path.stat()
    ext = file_path.suffix.lower()
    is_video_file = ext in VIDEO_EXTENSIONS
    is_image_file = ext in IMAGE_EXTENSIONS
    is_pdf_file = ext in PDF_EXTENSIONS

    metadata = {
        'name': file_path.name,
        'path': path_str,
        'file_path': path_str,
        'type': 'file',
        'extension': ext.lstrip('.'),
        'size': stat.st_size,
        'size_formatted': format_size(stat.st_size),
        'created_at': getattr(stat, 'st_birthtime', stat.st_ctime),
        'modified_at': stat.st_mtime,
        'ctime': getattr(stat, 'st_birthtime', stat.st_ctime),
        'mtime': stat.st_mtime,
        'is_video': is_video_file,
        'is_image': is_image_file,
        'is_pdf': is_pdf_file,
    }

    if is_video_file:
        video_info = get_cached_video_info(
            db,
            file_path,
            path_str,
            project_id=project_id,
            storage_scope=storage_scope,
            media_asset_id=media_asset_id,
            cache_identity=cache_identity,
        )
        metadata.update({
            'duration': video_info.get('duration', 0),
            'fps': video_info.get('fps', 0),
            'frames': video_info.get('frames', 0),
            'resolution': video_info.get('resolution', ''),
            'codec': video_info.get('codec', ''),
            'bit_depth': video_info.get('bit_depth', ''),
            'pixel_format': video_info.get('pixel_format', ''),
            'color_space': video_info.get('color_space', ''),
            'color_transfer': video_info.get('color_transfer', ''),
            'color_primaries': video_info.get('color_primaries', ''),
            'video_bitrate': video_info.get('video_bitrate', ''),
            'container_bitrate': video_info.get('container_bitrate', ''),
            'audio': video_info.get('audio'),
            'has_audio': video_info.get('has_audio', False),
        })
    elif is_image_file:
        try:
            probe_result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', str(file_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if probe_result.returncode == 0:
                probe_data = json.loads(probe_result.stdout)
                streams = probe_data.get('streams', [])
                if streams:
                    width = streams[0].get('width', 0)
                    height = streams[0].get('height', 0)
                    metadata['width'] = width
                    metadata['height'] = height
                    metadata['resolution'] = f'{width}x{height}'
        except Exception:
            pass

    return metadata
