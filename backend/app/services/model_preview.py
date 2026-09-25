"""Authorized companion files, browser-rendered thumbnails, and a bounded Alembic preview cache."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from functools import lru_cache
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

from app.db import SessionLocal
from app.models import TranscodeJob
from app.runtime_state import executor, transcode_processes, transcode_progress
from app.services.media import MODEL_EXTENSIONS, THUMBNAIL_WIDTH, get_file_hash
from app.services.media_resolution import source_signature, thumbnail_cache_path_for_identity, transcode_cache_path_for_identity
from app.services.storage_capacity import ensure_data_capacity
from app.services.upload_payloads import read_bounded_upload, require_valid_image
from app.services.transcode_lifecycle import (
    artifact_job_key, claim_transcode_job, mark_transcode_complete, mark_transcode_error,
    maybe_renew_transcode_claim, owns_transcode_claim, release_transcode_claim,
    restore_transcode_identity_for_authorized_source, touch_transcode_access,
    transcode_claim_is_active, transcode_identity_is_cancelled, transcode_publish_guard,
)

MAX_MODEL_BYTES = 128 * 1024 * 1024
MAX_ALEMBIC_BYTES = 2 * 1024**3
_lock = threading.Lock()
_pending: set[str] = set()
_ERROR = 'The Alembic preview could not be prepared. Export a polygon mesh cache with at most 2,400 frames and 250,000 triangles per frame, then retry.'


def _companion(source: Path, name: str) -> Path:
    parsed = urlsplit(name)
    name = unquote(name)
    parts = PurePosixPath(name).parts
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not parts
            or '\\' in name or '\x00' in name or name.startswith('/')
            or any(part.startswith('.') for part in parts)):
        raise HTTPException(422, 'Model companion files must be in the model folder or a subfolder. Export a self-contained GLB to avoid missing files.')
    root = source.parent.resolve()
    candidate = root.joinpath(*parts)
    if any(root.joinpath(*parts[:index]).is_symlink() for index in range(1, len(parts) + 1)):
        raise HTTPException(403, 'Model companion symlinks are not supported.')
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        raise HTTPException(403, 'Model companion is outside the model folder.') from None
    return candidate


def _json_document(source: Path):
    if source.suffix.lower() == '.glb':
        import struct
        with source.open('rb') as handle:
            header = handle.read(20)
            if len(header) != 20 or header[:4] != b'glTF':
                raise HTTPException(422, 'Invalid GLB file.')
            size, kind = struct.unpack('<II', header[12:20])
            if kind != 0x4e4f534a or size > 16 * 1024 * 1024:
                raise HTTPException(422, 'Invalid GLB metadata.')
            raw = handle.read(size)
    else:
        if source.stat().st_size > 16 * 1024 * 1024:
            raise HTTPException(422, 'The glTF metadata is too large. Export a GLB.')
        raw = source.read_bytes()
    try:
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get('asset', {}).get('version') != '2.0':
            raise ValueError()
        allocated = 0
        for entry in document.get('accessors', []):
            count = entry['count']
            width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}[entry['type']]
            if type(count) is not int or not 0 <= count <= 6_000_000:
                raise ValueError()
            allocated += count * width * 4
        if allocated > 256 * 1024 * 1024:
            raise HTTPException(413, 'The model geometry exceeds the browser preview budget. Export a lighter review model.')
        for entry in document.get('buffers', []) + document.get('images', []):
            if not isinstance(entry, dict) or not isinstance(entry.get('uri', ''), str):
                raise ValueError()
        return document
    except (ValueError, UnicodeError, TypeError, KeyError, AttributeError):
        raise HTTPException(422, 'Invalid glTF metadata.') from None


TEXTURE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.avif', '.bmp', '.tga', '.ktx2'}
# Arguments per MTL texture option. The file name follows the options.
_MTL_OPTIONS = {'-blendu': 1, '-blendv': 1, '-boost': 1, '-cc': 1, '-clamp': 1, '-imfchan': 1, '-texres': 1,
                '-type': 1, '-bm': 1, '-mm': 2, '-o': 3, '-s': 3, '-t': 3}


def _mtl_texture(value: str) -> str:
    """Return the file name that follows any MTL texture options."""
    fields = value.split()
    while fields and fields[0].lower() in _MTL_OPTIONS:
        count = _MTL_OPTIONS[fields.pop(0).lower()]
        taken = 0
        # -o, -s and -t take one to three numbers.
        while fields and taken < count and (taken == 0 or count < 3 or _is_number(fields[0])):
            fields.pop(0)
            taken += 1
    return ' '.join(fields)


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _fbx_textures(source: Path) -> list[tuple[str, ...]]:
    """Return the external image paths that FBX Video and Texture objects name."""
    import re
    import struct
    with source.open('rb') as handle:
        magic = handle.read(27)
        if not magic.startswith(b'Kaydara FBX Binary  \x00'):
            handle.seek(0)
            text = handle.read(MAX_MODEL_BYTES).decode('utf-8', 'replace')
            return [(name,) for name in re.findall(r'^\s*(?:RelativeFilename|FileName|Filename):\s*"([^"\n]{1,1024})"', text, re.M)]
        record = struct.Struct('<QQQB' if int.from_bytes(magic[23:27], 'little') >= 7500 else '<IIIB')
        end = source.stat().st_size
        visited = 0

        def children(offset, limit):
            nonlocal visited
            while offset + record.size <= limit:
                handle.seek(offset)
                stop, count, length, size = record.unpack(handle.read(record.size))
                visited += 1
                if stop == 0:
                    return
                if not offset < stop <= limit or visited > 2_000_000:
                    raise ValueError('Invalid FBX node')
                name = handle.read(size)
                yield name, count, length, offset + record.size + size, stop
                offset = stop

        def text(count, length, properties):
            handle.seek(properties)
            data = handle.read(min(length, 1029))
            size = int.from_bytes(data[1:5], 'little')
            return data[5:5 + size].decode('utf-8', 'replace') if count and data[:1] == b'S' and size <= 1024 else ''

        found, embedded_names = [], set()
        for name, _count, length, values, stop in children(27, end):
            if name != b'Objects':
                continue
            for kind, _count, length, values, last in children(values + length, stop):
                if kind not in {b'Video', b'Texture'}:
                    continue
                names, embedded = [], False
                for field, count, size, start, _stop in children(values + length, last):
                    if field in {b'RelativeFilename', b'Filename', b'FileName'}:
                        names.append(text(count, size, start))
                    elif field == b'Content':
                        handle.seek(start)
                        data = handle.read(5)
                        embedded = data[:1] == b'R' and int.from_bytes(data[1:5], 'little') > 0
                names = tuple(filter(None, names))
                if embedded:
                    embedded_names.update(names)
                elif names:
                    found.append(names)
        # A Texture object names the same file as its embedded Video object.
        return [names for names in found if embedded_names.isdisjoint(names)]


@lru_cache(maxsize=128)
def _references(path: str, signature: str):
    """Parse authored companion references once per model version."""
    source = Path(path)
    buffers, textures, materials = set(), [], []
    suffix = source.suffix.lower()
    if suffix in {'.gltf', '.glb'}:
        document = _json_document(source)
        for entry in document.get('buffers', []):
            uri = entry.get('uri')
            if uri and not uri.startswith('data:'):
                _companion(source, uri)
                buffers.add(unquote(uri))
        textures = [(unquote(entry['uri']),) for entry in document.get('images', []) if entry.get('uri') and not entry['uri'].startswith('data:')]
    elif suffix == '.obj':
        with source.open(encoding='utf-8', errors='replace') as handle:
            materials = list(dict.fromkeys(filter(None, (line[7:].strip() for line in handle if line.startswith('mtllib ')))))
    elif suffix == '.fbx':
        try:
            textures = _fbx_textures(source)
        except (OSError, ValueError, UnicodeError):
            textures = []
    if len(buffers) + len(textures) + len(materials) > 256:
        raise HTTPException(422, 'The model has too many companion files. Export a self-contained GLB.')
    return frozenset(buffers), tuple(textures), tuple(materials)


def _resolve(source: Path, reference: str, suffixes, folder: str = '') -> str | None:
    """Find an authored file in the model folder tree. Exporters often store
    absolute or Windows paths, so the file name alone is the fallback."""
    reference = reference.replace('\\', '/').strip()
    name = PurePosixPath(reference).name
    if not name or PurePosixPath(name).suffix.lower() not in suffixes:
        return None
    relative = (PurePosixPath(folder) / reference.removeprefix('./')).as_posix()
    for candidate in dict.fromkeys((relative, name, f'textures/{name}', f'Textures/{name}')):
        try:
            if _companion(source, candidate).is_file():
                return candidate
        except HTTPException:
            continue
    return None


def _dependencies(source: Path) -> dict:
    buffers, textures, libraries = _references(str(source), source_signature(source))
    # Geometry buffers are required. Material and texture files are optional:
    # the browser shows the mesh without a file that is missing or too large.
    total = source.stat().st_size
    for name in buffers:
        companion = _companion(source, name)
        if not companion.is_file():
            raise HTTPException(422, 'A model buffer file is missing. Upload the files that were exported with the model.')
        if companion.suffix.lower() not in TEXTURE_SUFFIXES | {'.bin', '.mtl'}:
            raise HTTPException(422, 'A companion file type is not supported. Export a self-contained GLB.')
        total += companion.stat().st_size
    if total > MAX_MODEL_BYTES:
        raise HTTPException(413, 'The model and its companion files exceed 128 MiB. Export a smaller review model.')
    names, materials, skipped = set(buffers), [], set()
    missing_materials, missing = 0, set()
    textures = [(alternatives, '') for alternatives in textures]

    def add(name: str, limit: int = MAX_MODEL_BYTES) -> bool:
        nonlocal total
        if name in names:
            return True
        size = _companion(source, name).stat().st_size
        if size > limit or total + size > MAX_MODEL_BYTES:
            skipped.add(name)
            return False
        total += size
        names.add(name)
        return True

    for library in libraries:
        found = _resolve(source, library, {'.mtl'})
        if not found:
            missing_materials += 1
        elif found not in names and add(found, 1024 * 1024):
            materials.append(found)
            folder = PurePosixPath(found).parent.as_posix()
            for line in _companion(source, found).read_text(errors='replace').splitlines():
                fields = line.strip().split(maxsplit=1)
                if len(fields) == 2 and fields[0].lower() in {'map_kd', 'map_ks', 'map_ke', 'map_d', 'map_bump', 'bump', 'norm', 'disp'}:
                    textures.append(((_mtl_texture(fields[1]),), folder))
    for alternatives, folder in textures:
        found = next(filter(None, (_resolve(source, reference, TEXTURE_SUFFIXES, folder) for reference in alternatives)), None)
        if found:
            add(found)
        elif alternatives:
            missing.add(PurePosixPath(alternatives[0].replace('\\', '/')).name.lower())
    if len(names) > 256:
        raise HTTPException(422, 'The model has too many companion files. Export a self-contained GLB.')
    return {'dependencies': sorted(names), 'materials': materials, 'missing_textures': len(missing),
            'missing_materials': missing_materials, 'skipped_files': len(skipped), 'bytes': total}


def model_cache_dir(key: str) -> Path:
    return transcode_cache_path_for_identity(key).with_suffix('.model')


def _decoder():
    return shutil.which('vueio-model-preview')


def _manifest(output):
    try:
        return json.loads((output / 'manifest.json').read_text())
    except (OSError, ValueError):
        return {}


def _prepare(source: Path, key: str, signature: str, decoder: str):
    attempt = None
    process = None
    succeeded = False
    output = model_cache_dir(key)
    try:
        with SessionLocal() as db:
            attempt = claim_transcode_job(db, job_key=key, output_path=output / 'manifest.json')
        if not attempt:
            return
        if _manifest(output).get('status') == 'complete':
            succeeded = mark_transcode_complete(attempt, output_path=output / 'manifest.json')
            return
        with transcode_publish_guard(key, attempt):
            shutil.rmtree(output, ignore_errors=True)
            output.mkdir(parents=True)
        ensure_data_capacity(512 * 1024 * 1024)
        process = subprocess.Popen([decoder, str(source), str(output)],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(output)})
        transcode_processes[key] = process
        started = heartbeat = time.time()
        while process.poll() is None:
            if time.time() - started > 300 or transcode_identity_is_cancelled(key) or not owns_transcode_claim(attempt):
                raise RuntimeError('Cancelled or timed out')
            heartbeat = maybe_renew_transcode_claim(attempt, heartbeat)
            ensure_data_capacity()
            transcode_progress[key]['progress'] = _manifest(output).get('progress', 0)
            time.sleep(.5)
        if process.returncode or _manifest(output).get('status') != 'complete':
            raise RuntimeError('Conversion failed')
        with transcode_publish_guard(key, attempt):
            if source_signature(source) != signature:
                raise RuntimeError('Source changed')
        succeeded = mark_transcode_complete(attempt, output_path=output / 'manifest.json', duration=_manifest(output).get('duration', 0))
    except Exception:
        if attempt:
            mark_transcode_error(attempt, error=_ERROR)
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait()
        if attempt:
            if not succeeded and owns_transcode_claim(attempt):
                with transcode_publish_guard(key, attempt, allow_cancelled=True):
                    shutil.rmtree(output, ignore_errors=True)
            release_transcode_claim(attempt)
        with _lock:
            _pending.discard(key)


def model_thumbnail_path(source: Path) -> Path:
    return thumbnail_cache_path_for_identity(f'model-thumbnail-v1:{source_signature(source)}')


def _require_model(full_path: Path | None) -> Path:
    if not full_path or not full_path.is_file():
        raise HTTPException(404, 'Model file not found.')
    if full_path.suffix.lower() not in MODEL_EXTENSIONS:
        raise HTTPException(415, 'This file is not a supported 3D model.')
    return full_path


def _thumbnail_state(source: Path, publisher: bool) -> dict:
    # Only a publisher learns that a thumbnail is missing, so only a publisher
    # spends bandwidth to render one. The token binds it to this model version.
    missing = publisher and not model_thumbnail_path(source).is_file()
    return {'needs_thumbnail': missing, 'thumbnail_generation': source_signature(source) if missing else ''}


async def save_model_thumbnail(full_path: Path | None, file: UploadFile, generation: str):
    """Store a browser-rendered thumbnail. Call ONLY after the route authorizes
    the source and confirms that the user may change its thumbnail."""
    source = _require_model(full_path)
    if generation != source_signature(source):
        raise HTTPException(409, 'The model changed. Open it again to update the thumbnail.')
    contents = await read_bounded_upload(file, max_bytes=2 * 1024 * 1024, empty_detail='The thumbnail is empty.', too_large_detail='The thumbnail is too large.')
    require_valid_image(contents, detail='The thumbnail is not a valid image.', allowed_formats={'JPEG', 'PNG', 'WEBP'})
    with Image.open(BytesIO(contents)) as image:
        if image.size != (THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 9 // 16):
            raise HTTPException(422, 'The thumbnail size is not valid.')
        image = image.convert('RGB')
    target = model_thumbnail_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'{target.stem}.{uuid4().hex}.tmp')
    try:
        image.save(temporary, format='JPEG', quality=88, optimize=True, progressive=True)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status': 'saved'}


def serve_model(full_path: Path | None, cache_identity: str | None, db, *, resource='manifest', name='', frame=0, generation='', retry=False, publisher=False):
    """Called ONLY after the normal file/share resolver authorizes the source."""
    source = _require_model(full_path)
    suffix = source.suffix.lower()
    limit = MAX_ALEMBIC_BYTES if suffix == '.abc' else MAX_MODEL_BYTES
    if source.stat().st_size > limit:
        raise HTTPException(413, 'This model is too large for a browser preview. Export a smaller review model.')
    headers = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}
    if resource == 'thumbnail':
        return JSONResponse({'format': suffix[1:], 'size': source.stat().st_size, **_thumbnail_state(source, publisher)}, headers=headers)
    if suffix != '.abc':
        if resource == 'source':
            return FileResponse(source, media_type='application/octet-stream', headers=headers)
        found = _dependencies(source)
        if resource == 'manifest':
            return JSONResponse({'format': suffix[1:], 'status': 'complete', **found, **_thumbnail_state(source, publisher)}, headers=headers)
        if resource == 'dependency' and name in found['dependencies']:
            return FileResponse(_companion(source, name), headers=headers)
        raise HTTPException(404, 'Model resource not found.')
    signature = source_signature(source)
    key = artifact_job_key(cache_identity or str(source), 'model', f'alembic-v1-{get_file_hash(signature)}')
    output = model_cache_dir(key)
    data = _manifest(output)
    token = get_file_hash(key)
    db.commit()
    touch_transcode_access(key)
    job = db.query(TranscodeJob).filter(TranscodeJob.file_path == key).first()
    if resource == 'frame':
        if generation != token or frame < 0 or frame >= data.get('ready_frames', 0):
            raise HTTPException(404, 'This model frame is not ready.')
        path = output / f'{frame:05}.bin.gz'
        if not path.is_file():
            raise HTTPException(404, 'This model frame is no longer cached. Reopen the model.')
        return FileResponse(path, media_type='application/octet-stream', headers={**headers, 'Content-Encoding': 'gzip'})
    if resource != 'manifest':
        raise HTTPException(404, 'Model resource not found.')
    if job and job.status == 'error' and not retry:
        return JSONResponse({'format': 'abc', 'status': 'error', 'error': _ERROR}, headers=headers)
    if data.get('status') != 'complete' and not transcode_claim_is_active(key):
        decoder = _decoder()
        if not decoder:
            raise HTTPException(503, 'The Alembic preview decoder is not installed on this server. Update the Vue.io engine to enable it.')
        restore_transcode_identity_for_authorized_source(key)
        with _lock:
            if not _pending:
                _pending.add(key)
                try:
                    executor.submit(_prepare, source, key, signature, decoder)
                except Exception:
                    _pending.discard(key)
                    raise
        data = {}  # A stale partial manifest must never look playable after restart.
    return JSONResponse({'format': 'abc', 'status': 'queued', 'ready_frames': 0, 'progress': 0, **data, 'generation': token,
                         **_thumbnail_state(source, publisher)}, headers=headers)
