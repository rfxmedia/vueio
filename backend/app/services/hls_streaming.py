from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import TranscodeJob
from app.runtime_state import executor, transcode_cancel_requested, transcode_processes, transcode_progress
from app.services.media import is_video, probe_duration_seconds
from app.services.media_resolution import source_signature
from app.services.media_resolution import hls_master_playlist_path_for_identity, hls_package_dir_for_identity
from app.services.storage_capacity import ensure_data_capacity
from app.services.transcode_lifecycle import (
    artifact_job_key,
    claim_transcode_job,
    enforce_transcode_cache_budget,
    mark_transcode_complete,
    mark_transcode_error,
    maybe_renew_transcode_claim,
    owns_transcode_claim,
    release_transcode_claim,
    restore_transcode_identity_for_authorized_source,
    transcode_claim_is_active,
    transcode_publish_guard,
    touch_transcode_access,
)

HLS_SEGMENT_SECONDS = 1.0
HLS_SHORT_CLIP_THRESHOLD_SECONDS = 2.0
HLS_SHORT_CLIP_MAX_FRAMES = 60
HLS_SHORT_CLIP_SEGMENT_SECONDS = 0.25
HLS_PACKAGE_PROFILE_VERSION = 'review-quality-v8-crf16'
HLS_GENERATION_RE = re.compile(r'^[0-9a-f]{12}$')
HLS_PACKAGE_METADATA = '.vueio-hls-package.json'
settings = get_settings()
HLS_STANDARD_RENDITIONS = [
    {'height': 1080, 'bitrate': '16000k', 'maxrate': '18000k', 'bufsize': '24000k', 'audio_bitrate': '160k'},
    {'height': 720, 'bitrate': '6000k', 'maxrate': '6600k', 'bufsize': '9000k', 'audio_bitrate': '128k'},
]


def _is_nonempty_file(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except Exception:
        return False


def _safe_rmtree(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except Exception:
        pass


def _directory_regular_file_bytes(path: Path) -> int:
    total = 0
    try:
        children = path.rglob('*')
        for child in children:
            try:
                if child.is_file() and not child.is_symlink():
                    total += child.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def _hls_package_pointer_path(package_dir: Path) -> Path:
    return package_dir.with_name(f'{package_dir.name}.current.json')


def _hls_package_index_path(package_id: str) -> Path:
    return settings.transcode_dir / f'{package_id}.hls.json'


def _read_hls_package_pointer_payload(package_dir: Path) -> dict | None:
    pointer_path = _hls_package_pointer_path(package_dir)
    try:
        data = json.loads(pointer_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _read_hls_package_pointer(package_dir: Path) -> Path | None:
    data = _read_hls_package_pointer_payload(package_dir)
    if not data:
        return None
    package_name = str(data.get('package_dir') or '')
    if not package_name or '/' in package_name or '\\' in package_name:
        return None
    if not package_name.startswith(f'{package_dir.name}.') or not package_name.endswith('.pkg'):
        return None
    resolved = (package_dir.parent / package_name).resolve()
    try:
        resolved.relative_to(package_dir.parent.resolve())
    except ValueError:
        return None
    return resolved if resolved.exists() and resolved.is_dir() else None


def _active_hls_package_dir(package_dir: Path) -> Path:
    return _read_hls_package_pointer(package_dir) or package_dir


def _new_hls_package_id() -> str:
    for _attempt in range(16):
        package_id = uuid4().hex[:12]
        if not _hls_package_index_path(package_id).exists():
            return package_id
    raise RuntimeError('could not allocate HLS package id')


def _write_hls_package_index(*, package_id: str, package_job_key: str, package_dir: Path) -> None:
    package_name = package_dir.name
    payload = {
        'package_id': package_id,
        'package_job_key': package_job_key,
        'package_dir': package_name,
        'profile': HLS_PACKAGE_PROFILE_VERSION,
        'published_at': time.time(),
    }
    (package_dir / HLS_PACKAGE_METADATA).write_text(json.dumps(payload), encoding='utf-8')
    index_path = _hls_package_index_path(package_id)
    index_tmp = index_path.with_name(f'{index_path.name}.{uuid4().hex}.tmp')
    try:
        index_tmp.write_text(json.dumps(payload), encoding='utf-8')
        index_tmp.replace(index_path)
    finally:
        try:
            index_tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _read_hls_package_index(package_id: str) -> dict | None:
    try:
        data = json.loads(_hls_package_index_path(package_id).read_text(encoding='utf-8'))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _hls_package_dir_from_generation(package_job_key: str, hls_generation: str) -> Path:
    generation = str(hls_generation or '').strip()
    if not HLS_GENERATION_RE.fullmatch(generation):
        raise HTTPException(status_code=400, detail='Invalid HLS generation')
    data = _read_hls_package_index(generation)
    if not data or data.get('package_job_key') != package_job_key:
        raise HTTPException(status_code=404, detail='HLS generation not found')
    package_name = str(data.get('package_dir') or '')
    if not package_name or '/' in package_name or '\\' in package_name:
        raise HTTPException(status_code=404, detail='HLS generation not found')
    package_dir = (settings.transcode_dir / package_name).resolve()
    try:
        package_dir.relative_to(settings.transcode_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail='HLS generation not found')
    if not package_dir.exists() or not package_dir.is_dir():
        raise HTTPException(status_code=404, detail='HLS generation not found')
    return package_dir


def _package_id_for_hls_dir(package_job_key: str, package_dir: Path) -> str:
    if not package_dir.exists() or not package_dir.is_dir():
        raise HTTPException(status_code=404, detail='HLS generation not found')
    try:
        data = json.loads((package_dir / HLS_PACKAGE_METADATA).read_text(encoding='utf-8'))
        package_id = str(data.get('package_id') or '').strip()
        if HLS_GENERATION_RE.fullmatch(package_id) and data.get('package_job_key') == package_job_key:
            index_data = _read_hls_package_index(package_id)
            if index_data and index_data.get('package_job_key') == package_job_key and index_data.get('package_dir') == package_dir.name:
                return package_id
            if not index_data:
                _write_hls_package_index(package_id=package_id, package_job_key=package_job_key, package_dir=package_dir)
                return package_id
    except Exception:
        pass

    pointer_payload = _read_hls_package_pointer_payload(hls_package_dir_for_identity(package_job_key)) or {}
    pointer_package_id = str(pointer_payload.get('package_id') or '').strip()
    if HLS_GENERATION_RE.fullmatch(pointer_package_id) and pointer_payload.get('package_dir') == package_dir.name:
        index_data = _read_hls_package_index(pointer_package_id)
        if index_data and index_data.get('package_job_key') == package_job_key and index_data.get('package_dir') == package_dir.name:
            return pointer_package_id
        if not index_data:
            _write_hls_package_index(package_id=pointer_package_id, package_job_key=package_job_key, package_dir=package_dir)
            return pointer_package_id

    package_id = _new_hls_package_id()
    _write_hls_package_index(package_id=package_id, package_job_key=package_job_key, package_dir=package_dir)
    return package_id


def _publish_hls_package(tmp_dir: Path, package_dir: Path, package_job_key: str) -> str:
    package_dir.parent.mkdir(parents=True, exist_ok=True)
    package_id = _new_hls_package_id()
    published_dir = package_dir.with_name(f'{package_dir.name}.{package_id}.pkg')
    pointer_path = _hls_package_pointer_path(package_dir)
    pointer_tmp = pointer_path.with_name(f'{pointer_path.name}.{uuid4().hex}.tmp')
    try:
        tmp_dir.replace(published_dir)
        _write_hls_package_index(package_id=package_id, package_job_key=package_job_key, package_dir=published_dir)
        pointer_payload = {
            'package_id': package_id,
            'package_base_id': package_dir.name,
            'package_dir': published_dir.name,
            'package_job_key': package_job_key,
            'profile': HLS_PACKAGE_PROFILE_VERSION,
            'published_at': time.time(),
        }
        pointer_tmp.write_text(json.dumps(pointer_payload), encoding='utf-8')
        pointer_tmp.replace(pointer_path)
        package_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        _safe_rmtree(published_dir)
        try:
            _hls_package_index_path(package_id).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        try:
            pointer_tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return package_id


def _package_profile_marker_path(package_dir: Path) -> Path:
    return package_dir / '.vueio-hls-profile'


def _write_package_profile_marker(package_dir: Path) -> None:
    _package_profile_marker_path(package_dir).write_text(HLS_PACKAGE_PROFILE_VERSION, encoding='utf-8')


def _package_has_current_profile(package_dir: Path) -> bool:
    try:
        return _package_profile_marker_path(package_dir).read_text(encoding='utf-8').strip() == HLS_PACKAGE_PROFILE_VERSION
    except Exception:
        return False


def _probe_video_streams(input_path: Path) -> dict:
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(input_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {'duration': 0.0, 'width': 0, 'height': 0, 'fps': 24.0, 'frames': 0, 'has_audio': False}
        data = json.loads(result.stdout)
    except Exception:
        return {'duration': 0.0, 'width': 0, 'height': 0, 'fps': 24.0, 'frames': 0, 'has_audio': False}

    duration = probe_duration_seconds(data)
    width = 0
    height = 0
    fps = 24.0
    frames = 0
    has_audio = False
    video_stream = None
    for stream in data.get('streams', []):
        codec_type = str(stream.get('codec_type') or '').lower()
        if codec_type == 'audio':
            has_audio = True
            continue
        if codec_type == 'video' and video_stream is None:
            video_stream = stream

    if video_stream:
        width = int(video_stream.get('width') or 0)
        height = int(video_stream.get('height') or 0)
        try:
            frames = int(video_stream.get('nb_frames') or 0)
        except Exception:
            frames = 0
        fps_str = str(video_stream.get('r_frame_rate') or '24/1')
        if '/' in fps_str:
            num, den = fps_str.split('/', 1)
            try:
                den_value = float(den)
                fps = float(num) / den_value if den_value > 0 else 24.0
            except Exception:
                fps = 24.0

    return {
        'duration': duration,
        'width': width,
        'height': height,
        'fps': fps if fps > 0 else 24.0,
        'frames': frames,
        'has_audio': has_audio,
    }


def _pick_hls_renditions(source_height: int) -> list[dict]:
    normalized_source_height = int(source_height or 0)
    if normalized_source_height <= 0:
        return [dict(HLS_STANDARD_RENDITIONS[-1])]

    variants = [dict(item) for item in HLS_STANDARD_RENDITIONS if item['height'] <= normalized_source_height]
    if not variants:
        target_height = max(240, normalized_source_height - (normalized_source_height % 2))
        if target_height >= 540:
            variants = [{
                'height': target_height,
                'bitrate': '1800k',
                'maxrate': '1926k',
                'bufsize': '2700k',
                'audio_bitrate': '96k',
            }]
        elif target_height >= 360:
            variants = [{
                'height': target_height,
                'bitrate': '900k',
                'maxrate': '963k',
                'bufsize': '1350k',
                'audio_bitrate': '96k',
            }]
        else:
            variants = [{
                'height': target_height,
                'bitrate': '500k',
                'maxrate': '550k',
                'bufsize': '750k',
                'audio_bitrate': '64k',
            }]

    return variants


def _expected_hls_heights(source_height: int) -> set[int]:
    return {int(item.get('height') or 0) for item in _pick_hls_renditions(source_height) if int(item.get('height') or 0) > 0}


def _is_short_hls_clip(probe: dict) -> bool:
    duration = float(probe.get('duration') or 0)
    frames = int(probe.get('frames') or 0)
    return (0 < duration <= HLS_SHORT_CLIP_THRESHOLD_SECONDS) or (0 < frames <= HLS_SHORT_CLIP_MAX_FRAMES)


def _hls_segment_seconds_for_probe(probe: dict) -> float:
    return HLS_SHORT_CLIP_SEGMENT_SECONDS if _is_short_hls_clip(probe) else HLS_SEGMENT_SECONDS


def _hls_gop_frames_for_probe(probe: dict) -> int:
    if _is_short_hls_clip(probe):
        return 1
    fps = float(probe.get('fps') or 24.0)
    return max(12, int(round(fps * HLS_SEGMENT_SECONDS)))


def _format_hls_seconds(value: float) -> str:
    return f'{float(value):.3f}'.rstrip('0').rstrip('.')


def _read_master_playlist(master_playlist: Path) -> str:
    try:
        return master_playlist.read_text(encoding='utf-8')
    except Exception:
        return ''


def _master_playlist_resolutions(master_playlist: Path) -> set[tuple[int, int]]:
    content = _read_master_playlist(master_playlist)
    if not content:
        return set()

    resolutions: set[tuple[int, int]] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if 'RESOLUTION=' not in line:
            continue
        try:
            resolution_part = line.split('RESOLUTION=', 1)[1].split(',', 1)[0].strip()
            width_str, height_str = resolution_part.lower().split('x', 1)
            resolutions.add((int(width_str), int(height_str)))
        except Exception:
            continue
    return resolutions


def _master_playlist_has_audio(master_playlist: Path) -> bool:
    content = _read_master_playlist(master_playlist)
    if not content:
        return False
    return 'mp4a' in content.lower()


def _master_playlist_has_expected_renditions(master_playlist: Path, source_height: int, has_audio: bool) -> bool:
    resolutions = _master_playlist_resolutions(master_playlist)
    if not resolutions:
        return False

    expected_heights = _expected_hls_heights(source_height)
    actual_heights = {height for _width, height in resolutions if height > 0}
    if actual_heights != expected_heights:
        return False

    if has_audio and not _master_playlist_has_audio(master_playlist):
        return False

    return True


def hls_job_key(source_identity: str) -> str:
    return artifact_job_key(source_identity, 'hls', HLS_PACKAGE_PROFILE_VERSION)


def _adopt_legacy_hls_artifact(db: Session, *, legacy_job_key: str, artifact_job_key: str, probe: dict, package_dir: Path, master_playlist: Path) -> bool:
    if legacy_job_key == artifact_job_key:
        return False
    active_package_dir = _active_hls_package_dir(package_dir)
    active_master_playlist = active_package_dir / 'master.m3u8'
    if _is_nonempty_file(active_master_playlist) and validate_hls_package(active_package_dir, probe):
        return True
    if transcode_claim_is_active(artifact_job_key):
        return False

    legacy_job = db.query(TranscodeJob).filter(TranscodeJob.file_path == legacy_job_key).first()
    candidates: list[Path] = []
    if legacy_job and legacy_job.status == 'complete' and legacy_job.output_path:
        candidates.append(Path(legacy_job.output_path).parent)
    candidates.append(hls_package_dir_for_identity(legacy_job_key))
    legacy_package = next((path for path in candidates if _is_nonempty_file(path / 'master.m3u8') and validate_hls_package(path, probe)), None)
    if legacy_package is None:
        return False
    ensure_data_capacity(max(1024 * 1024, _directory_regular_file_bytes(legacy_package)))

    attempt = claim_transcode_job(db, job_key=artifact_job_key, output_path=master_playlist)
    if attempt is None:
        return False

    tmp_copy = package_dir.with_name(f'{package_dir.name}.{attempt.attempt_id}.{uuid4().hex}.migrate')
    try:
        _safe_rmtree(tmp_copy)
        shutil.copytree(legacy_package, tmp_copy)
        if not validate_hls_package(tmp_copy, probe):
            raise RuntimeError('legacy HLS artifact validation failed')
        with transcode_publish_guard(artifact_job_key, attempt):
            if not validate_hls_package(tmp_copy, probe):
                raise RuntimeError('legacy HLS artifact validation failed')
            _publish_hls_package(tmp_copy, package_dir, artifact_job_key)
            tmp_copy = None

        active_master_playlist = _active_hls_package_dir(package_dir) / 'master.m3u8'

        job = db.query(TranscodeJob).filter(TranscodeJob.file_path == artifact_job_key).first()
        if not job:
            job = TranscodeJob(file_path=artifact_job_key, created_at=time.time())
            db.add(job)
        job.status = 'complete'
        job.progress = 100
        job.output_path = str(active_master_playlist)
        job.last_accessed = time.time()
        if legacy_job:
            job.duration = legacy_job.duration or job.duration or 0
            db.delete(legacy_job)
        db.commit()
        enforce_transcode_cache_budget(db)
        return True
    except Exception as exc:
        mark_transcode_error(attempt, error=str(exc))
        return False
    finally:
        if tmp_copy is not None:
            _safe_rmtree(tmp_copy)
        release_transcode_claim(attempt)


def _playlist_media_entries(playlist: Path) -> list[str]:
    try:
        content = playlist.read_text(encoding='utf-8')
    except Exception:
        return []
    entries: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        entries.append(line)
    return entries


def _safe_package_child(package_dir: Path, rel_path: str) -> Path | None:
    try:
        root = package_dir.resolve()
        child = (root / rel_path).resolve()
        child.relative_to(root)
        return child
    except Exception:
        return None


def validate_hls_package(package_dir: Path, probe: dict) -> bool:
    master_playlist = package_dir / 'master.m3u8'
    if not _is_nonempty_file(master_playlist) or not _package_has_current_profile(package_dir):
        return False
    if not _master_playlist_has_expected_renditions(master_playlist, int(probe.get('height') or 0), bool(probe.get('has_audio'))):
        return False

    master_entries = _playlist_media_entries(master_playlist)
    if not master_entries:
        return False
    expected_variant_count = len(_expected_hls_heights(int(probe.get('height') or 0)))
    if len(master_entries) != expected_variant_count:
        return False

    for variant_entry in master_entries:
        if variant_entry.startswith(('http://', 'https://', '/')) or '..' in Path(variant_entry).parts:
            return False
        variant_path = _safe_package_child(package_dir, variant_entry)
        if variant_path is None or variant_path.suffix.lower() != '.m3u8' or not _is_nonempty_file(variant_path):
            return False
        try:
            variant_content = variant_path.read_text(encoding='utf-8')
        except Exception:
            return False
        if '#EXTM3U' not in variant_content or '#EXT-X-ENDLIST' not in variant_content:
            return False
        segment_entries = _playlist_media_entries(variant_path)
        if not segment_entries:
            return False
        for segment_entry in segment_entries:
            if segment_entry.startswith(('http://', 'https://', '/')) or '..' in Path(segment_entry).parts:
                return False
            segment_path = _safe_package_child(package_dir, segment_entry)
            if segment_path is None or not _is_nonempty_file(segment_path):
                return False
    return True


def _build_hls_output_args(package_dir: Path, renditions: list[dict], has_audio: bool, *, segment_seconds: float) -> list[str]:
    var_stream_map = ' '.join(
        f'v:{index},a:{index}' if has_audio else f'v:{index}'
        for index in range(len(renditions))
    )
    return [
        '-muxdelay', '0',
        '-muxpreload', '0',
        '-avoid_negative_ts', 'make_zero',
        '-f', 'hls',
        '-hls_time', _format_hls_seconds(segment_seconds),
        '-hls_playlist_type', 'vod',
        '-hls_flags', 'independent_segments',
        '-master_pl_name', 'master.m3u8',
        '-var_stream_map', var_stream_map,
        '-hls_segment_filename', str(package_dir / 'segment_%v_%03d.ts'),
        '-progress', 'pipe:1',
        str(package_dir / 'variant_%v.m3u8'),
    ]


def _bitrate_to_int(value: str, fallback: int) -> int:
    text = str(value or '').strip().lower()
    try:
        if text.endswith('k'):
            return int(float(text[:-1]) * 1000)
        if text.endswith('m'):
            return int(float(text[:-1]) * 1_000_000)
        return int(float(text))
    except Exception:
        return fallback


def _scaled_even_width(source_width: int, source_height: int, target_height: int) -> int:
    if source_width <= 0 or source_height <= 0 or target_height <= 0:
        return max(2, int(target_height * 16 / 9) // 2 * 2)
    width = int(source_width * target_height / source_height)
    if width % 2:
        width -= 1
    return max(2, width)


def _codec_string_for_hls(height: int, has_audio: bool) -> str:
    if height >= 1080:
        video_codec = 'avc1.640028'
    elif height >= 720:
        video_codec = 'avc1.64001f'
    else:
        video_codec = 'avc1.64001e'
    return f'{video_codec},mp4a.40.2' if has_audio else video_codec


def _repair_variant_target_durations(package_dir: Path) -> None:
    for playlist in sorted(package_dir.glob('variant_*.m3u8')):
        try:
            content = playlist.read_text(encoding='utf-8')
        except Exception:
            continue
        durations = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line.startswith('#EXTINF:'):
                continue
            try:
                durations.append(float(line.split(':', 1)[1].split(',', 1)[0]))
            except Exception:
                pass
        if not durations:
            continue
        target_duration = max(1, int(max(durations) + 0.999999))
        lines = []
        replaced = False
        changed = False
        for raw_line in content.splitlines():
            if raw_line.startswith('#EXT-X-TARGETDURATION:'):
                replaced = True
                try:
                    current_value = int(float(raw_line.split(':', 1)[1]))
                except Exception:
                    current_value = 0
                if current_value < target_duration:
                    lines.append(f'#EXT-X-TARGETDURATION:{target_duration}')
                    changed = True
                else:
                    lines.append(raw_line)
            else:
                lines.append(raw_line)
        if not replaced:
            insert_at = 2 if len(lines) >= 2 else len(lines)
            lines.insert(insert_at, f'#EXT-X-TARGETDURATION:{target_duration}')
            changed = True
        if changed:
            playlist.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _write_fallback_master_playlist_if_needed(package_dir: Path, probe: dict) -> None:
    master_playlist = package_dir / 'master.m3u8'
    if _master_playlist_resolutions(master_playlist):
        return

    source_width = int(probe.get('width') or 0)
    source_height = int(probe.get('height') or 0)
    has_audio = bool(probe.get('has_audio'))
    renditions = _pick_hls_renditions(source_height)

    lines = ['#EXTM3U', '#EXT-X-VERSION:6']
    wrote_variant = False
    for index, rendition in enumerate(renditions):
        variant_name = f'variant_{index}.m3u8'
        if not _is_nonempty_file(package_dir / variant_name):
            continue
        height = int(rendition.get('height') or 0)
        width = _scaled_even_width(source_width, source_height, height)
        average_bandwidth = _bitrate_to_int(rendition.get('bitrate', ''), 1_000_000)
        max_bandwidth = _bitrate_to_int(rendition.get('maxrate', ''), average_bandwidth)
        if has_audio:
            audio_bandwidth = _bitrate_to_int(rendition.get('audio_bitrate', ''), 128_000)
            average_bandwidth += audio_bandwidth
            max_bandwidth += audio_bandwidth
        codecs = _codec_string_for_hls(height, has_audio)
        lines.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={max_bandwidth},'
            f'AVERAGE-BANDWIDTH={average_bandwidth},'
            f'RESOLUTION={width}x{height},'
            f'CODECS="{codecs}"'
        )
        lines.append(variant_name)
        lines.append('')
        wrote_variant = True

    if wrote_variant:
        master_playlist.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')


def _repair_hls_package_playlists(package_dir: Path, probe: dict) -> None:
    _repair_variant_target_durations(package_dir)
    _write_fallback_master_playlist_if_needed(package_dir, probe)


def _build_hls_ffmpeg_command_cpu(input_path: Path, package_dir: Path, probe: dict) -> list[str]:
    renditions = _pick_hls_renditions(int(probe.get('height') or 0))
    has_audio = bool(probe.get('has_audio'))
    segment_seconds = _hls_segment_seconds_for_probe(probe)
    gop = _hls_gop_frames_for_probe(probe)
    force_keyframe_expr = f'expr:gte(t,n_forced*{_format_hls_seconds(segment_seconds)})'

    cmd = ['ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'error', '-y', '-fflags', '+genpts', '-i', str(input_path)]

    if len(renditions) > 1:
        split_labels = ''.join(f'[vsplit{index}]' for index in range(len(renditions)))
        filter_parts = [f'[0:v:0]split={len(renditions)}{split_labels}']
        for index, rendition in enumerate(renditions):
            filter_parts.append(
                f'[vsplit{index}]scale=-2:{rendition["height"]}:flags=lanczos[vout{index}]'
            )
        cmd.extend(['-filter_complex', ';'.join(filter_parts)])
        for index in range(len(renditions)):
            cmd.extend(['-map', f'[vout{index}]'])
            if has_audio:
                cmd.extend(['-map', '0:a:0?'])
    else:
        cmd.extend(['-map', '0:v:0'])
        if has_audio:
            cmd.extend(['-map', '0:a:0?'])

    for index, rendition in enumerate(renditions):
        cmd.extend([
            f'-c:v:{index}', 'libx264',
            f'-preset:v:{index}', 'medium',
            f'-profile:v:{index}', 'high',
            f'-pix_fmt:v:{index}', 'yuv420p',
            f'-crf:v:{index}', '16',
            f'-sc_threshold:v:{index}', '0',
            f'-g:v:{index}', str(gop),
            f'-keyint_min:v:{index}', str(gop),
            f'-bf:v:{index}', '0',
            f'-force_key_frames:v:{index}', force_keyframe_expr,
            f'-b:v:{index}', rendition['bitrate'],
            f'-maxrate:v:{index}', rendition['maxrate'],
            f'-bufsize:v:{index}', rendition['bufsize'],
        ])
        if len(renditions) == 1:
            cmd.extend([f'-vf:v:{index}', f'scale=-2:{rendition["height"]}:flags=lanczos'])
        if has_audio:
            cmd.extend([
                f'-c:a:{index}', 'aac',
                f'-b:a:{index}', rendition['audio_bitrate'],
                f'-ac:a:{index}', '2',
                f'-ar:a:{index}', '48000',
            ])

    cmd.extend(_build_hls_output_args(package_dir, renditions, has_audio, segment_seconds=segment_seconds))
    return cmd


def _build_hls_ffmpeg_command(input_path: Path, package_dir: Path, probe: dict) -> list[str]:
    return _build_hls_ffmpeg_command_cpu(input_path, package_dir, probe)


def _estimated_hls_output_bytes(input_path: Path, probe: dict) -> int:
    duration = float(probe.get('duration') or 0)
    if duration <= 0:
        try:
            return max(1024 * 1024, input_path.stat().st_size * 2)
        except OSError:
            return 1024 * 1024

    has_audio = bool(probe.get('has_audio'))
    bits_per_second = 0
    for rendition in _pick_hls_renditions(int(probe.get('height') or 0)):
        bits_per_second += _bitrate_to_int(rendition.get('maxrate', ''), 1_000_000)
        if has_audio:
            bits_per_second += _bitrate_to_int(rendition.get('audio_bitrate', ''), 128_000)
    return max(1024 * 1024, int(duration * bits_per_second / 8 * 1.15))


def _start_or_restart_stream_job(db: Session, job_key: str) -> TranscodeJob:
    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == job_key).first()
    if not job:
        job = TranscodeJob(file_path=job_key, status='processing', progress=0, output_path=None, duration=0, created_at=time.time())
        db.add(job)
    else:
        job.status = 'processing'
        job.progress = 0
        job.output_path = None
        job.created_at = time.time()
    db.commit()
    return job


def package_video_to_hls_with_progress(input_path: Path, package_dir: Path, job_key: str, expected_source_signature: str | None = None):
    attempt = None
    tmp_dir = None
    try:
        with SessionLocal() as session:
            attempt = claim_transcode_job(session, job_key=job_key, output_path=package_dir / 'master.m3u8')
        if attempt is None:
            return False

        probe = _probe_video_streams(input_path)
        ensure_data_capacity(_estimated_hls_output_bytes(input_path, probe))
        duration = float(probe.get('duration') or 0)
        current_state = transcode_progress.get(job_key, {})
        transcode_progress[job_key] = {**current_state, 'progress': 0, 'status': 'processing', 'duration': duration}

        tmp_dir = package_dir.with_name(f'{package_dir.name}.{attempt.attempt_id}.{uuid4().hex}.part')
        _safe_rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        tail = deque(maxlen=80)
        cmd = _build_hls_ffmpeg_command(input_path, tmp_dir, probe)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        transcode_processes[job_key] = process
        last_heartbeat = time.time()
        if process.stdout:
            for line in process.stdout:
                if job_key in transcode_cancel_requested or not owns_transcode_claim(attempt):
                    process.terminate()
                    break
                last_heartbeat = maybe_renew_transcode_claim(attempt, last_heartbeat)
                line = (line or '').strip()
                if line:
                    tail.append(line)
                if line.startswith('out_time_ms='):
                    try:
                        ensure_data_capacity()
                    except HTTPException:
                        process.terminate()
                        raise
                    try:
                        time_ms = int(line.split('=', 1)[1].strip())
                        if duration > 0:
                            progress = min(99, (time_ms / 1_000_000 / duration) * 100)
                            transcode_progress[job_key]['progress'] = round(progress, 1)
                    except Exception:
                        pass
        returncode = process.wait()

        if returncode == 0:
            _repair_hls_package_playlists(tmp_dir, probe)
            _write_package_profile_marker(tmp_dir)

        master_playlist = tmp_dir / 'master.m3u8'
        if returncode == 0 and _is_nonempty_file(master_playlist) and validate_hls_package(tmp_dir, probe):
            with transcode_publish_guard(job_key, attempt):
                if job_key in transcode_cancel_requested or not owns_transcode_claim(attempt):
                    raise RuntimeError('HLS attempt was cancelled')
                if expected_source_signature and source_signature(input_path) != expected_source_signature:
                    raise RuntimeError('source generation changed before publish')
                if not validate_hls_package(tmp_dir, probe):
                    raise RuntimeError('HLS package validation failed before publish')
                _publish_hls_package(tmp_dir, package_dir, job_key)
                tmp_dir = None
                output_path = _active_hls_package_dir(package_dir) / 'master.m3u8'
            return mark_transcode_complete(attempt, output_path=output_path, duration=duration)

        err_tail = '\n'.join(list(tail)[-20:]) if tail else ''
        mark_transcode_error(attempt, error=err_tail or f'ffmpeg rc={returncode}', duration=duration)
        return False
    except Exception as exc:
        if attempt is not None:
            mark_transcode_error(attempt, error=str(exc))
        else:
            transcode_progress[job_key] = {'progress': 0, 'status': 'error', 'error': str(exc), 'completed_at': time.time()}
        return False
    finally:
        if tmp_dir is not None:
            _safe_rmtree(tmp_dir)
        if attempt is not None:
            release_transcode_claim(attempt)


def ensure_hls_package_running(db: Session, *, job_key: str, input_path: Path) -> bool:
    package_job_key = hls_job_key(job_key)
    restore_transcode_identity_for_authorized_source(package_job_key)
    package_dir = hls_package_dir_for_identity(package_job_key)
    master_playlist = hls_master_playlist_path_for_identity(package_job_key)
    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == package_job_key).first()
    force_restart = False

    probe = _probe_video_streams(input_path)
    _adopt_legacy_hls_artifact(db, legacy_job_key=job_key, artifact_job_key=package_job_key, probe=probe, package_dir=package_dir, master_playlist=master_playlist)
    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == package_job_key).first()

    active_package_dir = _active_hls_package_dir(package_dir)
    active_master_playlist = active_package_dir / 'master.m3u8'

    if _is_nonempty_file(active_master_playlist):
        if validate_hls_package(active_package_dir, probe):
            if not job:
                job = TranscodeJob(
                    file_path=package_job_key,
                    status='complete',
                    progress=100,
                    output_path=str(active_master_playlist),
                    duration=0,
                    created_at=time.time(),
                    last_accessed=time.time(),
                )
                db.add(job)
                db.commit()
                enforce_transcode_cache_budget(db)
            elif job.status != 'complete' and not transcode_claim_is_active(package_job_key):
                job.status = 'complete'
                job.output_path = str(active_master_playlist)
                job.progress = 100
                job.last_accessed = time.time()
                db.commit()
                enforce_transcode_cache_budget(db)
            return True
        force_restart = True

    if job:
        if job.status == 'complete' and not _is_nonempty_file(Path(job.output_path or '')):
            force_restart = True
        elif job.status in {'error', 'pending'}:
            force_restart = True
        elif job.status == 'processing':
            if transcode_claim_is_active(package_job_key):
                return False
            force_restart = True

    if not job or force_restart:
        ensure_data_capacity(_estimated_hls_output_bytes(input_path, probe))
        if force_restart:
            transcode_progress.pop(package_job_key, None)
        _start_or_restart_stream_job(db, package_job_key)

    inflight = transcode_progress.get(package_job_key) or {}
    if inflight.get('status') != 'processing':
        expected_generation = source_signature(input_path)
        executor.submit(package_video_to_hls_with_progress, input_path, package_dir, package_job_key, expected_generation)

    return False


def get_hls_status(db: Session, *, job_key: str, input_path: Path | None) -> dict:
    if not input_path or not input_path.exists():
        raise HTTPException(status_code=404, detail='File not found')
    if not is_video(input_path):
        raise HTTPException(status_code=400, detail='HLS playback is only available for video files')

    if ensure_hls_package_running(db, job_key=job_key, input_path=input_path):
        return {'status': 'complete', 'progress': 100}

    package_job_key = hls_job_key(job_key)
    inflight = transcode_progress.get(package_job_key)
    if inflight:
        return inflight

    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == package_job_key).first()
    if not job:
        return {'status': 'pending', 'progress': 0}
    return {'status': job.status, 'progress': job.progress}


def _rewrite_playlist_content(content: str, build_asset_url) -> str:
    lines = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            lines.append(raw_line)
            continue
        lines.append(build_asset_url(line))
    return '\n'.join(lines) + '\n'


def build_hls_asset_response(package_dir: Path, asset_path: str, build_asset_url):
    package_root = package_dir.resolve()
    resolved_path = (package_root / asset_path).resolve()
    try:
        resolved_path.relative_to(package_root)
    except ValueError:
        raise HTTPException(status_code=403, detail='Access denied')
    if not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail='HLS asset not found')

    if resolved_path.suffix.lower() == '.m3u8':
        content = resolved_path.read_text(encoding='utf-8')
        rewritten = _rewrite_playlist_content(content, build_asset_url)
        return Response(
            content=rewritten,
            media_type='application/vnd.apple.mpegurl',
            headers={'Cache-Control': 'no-store, max-age=0'},
        )

    media_type = 'video/mp2t' if resolved_path.suffix.lower() == '.ts' else 'application/octet-stream'
    return FileResponse(
        resolved_path,
        media_type=media_type,
        headers={'Cache-Control': 'private, max-age=3600, immutable'},
    )


def get_hls_manifest_response(db: Session, *, job_key: str, input_path: Path, build_asset_url):
    status = get_hls_status(db, job_key=job_key, input_path=input_path)
    if str(status.get('status') or '').lower() != 'complete':
        raise HTTPException(status_code=409, detail='HLS package is not ready')
    package_job_key = hls_job_key(job_key)
    package_dir = hls_package_dir_for_identity(hls_job_key(job_key))
    active_package_dir = _active_hls_package_dir(package_dir)
    generation = _package_id_for_hls_dir(package_job_key, active_package_dir)

    def build_generation_asset_url(asset_path: str) -> str:
        url = build_asset_url(asset_path)
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query['hls_generation'] = generation
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    response = build_hls_asset_response(active_package_dir, 'master.m3u8', build_generation_asset_url)
    touch_transcode_access(package_job_key)
    return response


def get_hls_asset_response(*, job_key: str, asset_path: str, build_asset_url, hls_generation: str | None = None):
    package_job_key = hls_job_key(job_key)
    if hls_generation:
        generation = str(hls_generation or '').strip()
        package_dir = _hls_package_dir_from_generation(package_job_key, generation)
    else:
        package_dir = _active_hls_package_dir(hls_package_dir_for_identity(package_job_key))
        generation = _package_id_for_hls_dir(package_job_key, package_dir)

    def build_generation_asset_url(next_asset_path: str) -> str:
        url = build_asset_url(next_asset_path)
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query['hls_generation'] = generation
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    response = build_hls_asset_response(package_dir, asset_path, build_generation_asset_url)
    touch_transcode_access(package_job_key)
    return response


def get_hls_thumbnail_source(job_key: str) -> Path | None:
    package_job_key = hls_job_key(job_key)
    package_dir = hls_package_dir_for_identity(package_job_key)
    package_dir = _active_hls_package_dir(package_dir)
    master_playlist = package_dir / 'master.m3u8'
    if not _is_nonempty_file(master_playlist) or not _package_has_current_profile(package_dir):
        return None

    variants: list[tuple[int, Path]] = []
    pending_height = 0
    for raw_line in _read_master_playlist(master_playlist).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith('#EXT-X-STREAM-INF:'):
            pending_height = 0
            if 'RESOLUTION=' in line:
                try:
                    resolution_part = line.split('RESOLUTION=', 1)[1].split(',', 1)[0].strip()
                    _width_str, height_str = resolution_part.lower().split('x', 1)
                    pending_height = int(height_str)
                except Exception:
                    pending_height = 0
            continue
        if line.startswith('#') or not pending_height:
            continue
        variant_path = (package_dir / line).resolve()
        if str(variant_path).startswith(str(package_dir.resolve())) and _is_nonempty_file(variant_path):
            variants.append((pending_height, variant_path))
        pending_height = 0

    if not variants:
        return None
    return sorted(variants, key=lambda item: item[0])[0][1]
