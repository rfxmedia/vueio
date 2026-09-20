"""Comparison exports use the existing render leases, cache and source authorization.

A signed receipt holds the small export recipe, not a second job database. Every
request must still resolve both source versions and authorize their download.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import time
import uuid
from typing import Literal

from fastapi import HTTPException, Request
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings
from app.limiter import enforce_rate_limit
from app.services.comparison import Comparison, comparison_status
from app.services.media_encoding import validate_recipe
from app.services.transcode_lifecycle import purge_transcode_identity, tombstone_transcode_identity, transcode_publish_guard


class ExportOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    mode: Literal['wipe', 'side-by-side'] = 'wipe'
    aspect: Literal['source', '3:4', '1:1', '16:9'] = 'source'
    start_frame: int = Field(default=0, ge=0, strict=True)
    end_frame: int = Field(ge=1, strict=True)
    freeze_frame: int | None = Field(default=None, ge=0, strict=True)
    freeze_frames: int = Field(default=120, ge=2, le=36000, strict=True)
    wipe_start: float = Field(default=.4, ge=0, le=1)
    wipe_duration: float = Field(default=.2, gt=0, le=1)
    swapped: bool = Field(default=False, strict=True)


def _geometry(pair: Comparison, options: ExportOptions) -> tuple[int, int, bool]:
    sizes = pair.info['source_sizes']
    width, height = sizes[int(options.swapped)]
    split = options.mode == 'side-by-side'
    ratios = {'3:4': (3, 4), '1:1': (1, 1), '16:9': (16, 9)}
    if options.aspect == 'source':
        panes = 2 if split else 1
        portrait = width * panes < height
        scale = min(1, (1080 if portrait else 1920) / (width * panes), (1920 if portrait else 1080) / height)
        return max(2, int(width * scale / 2) * 2) * panes, max(2, int(height * scale / 2) * 2), False
    rw, rh = ratios[options.aspect]
    ratio = rw / rh
    def area(w, h):
        return sum(min(w / sw, h / sh) ** 2 * sw * sh for sw, sh in sizes)
    stacked = split and area(ratio, .5) > area(ratio / 2, 1) * 1.01
    unit = 4 if split and (rh if stacked else rw) * 2 % 4 else 2
    size = min((1080 if ratio < 1 else 1920) / rw, (1920 if ratio < 1 else 1080) / rh)
    pw, ph = rw * size / (2 if split and not stacked else 1), rh * size / (2 if stacked else 1)
    fit = max(min(pw / sw, ph / sh) for sw, sh in sizes)
    k = max(unit, int(size * min(1, 1 / fit) / unit) * unit)
    return rw * k, rh * k, stacked


def _recipe(pair: Comparison, options: ExportOptions, artwork: bool) -> dict:
    frozen = options.freeze_frame is not None
    frames = options.freeze_frames if frozen else options.end_frame - options.start_frame
    source_start = options.freeze_frame if frozen else options.start_frame
    source_end = source_start + 1 if frozen else options.end_frame
    if frames < 2 or source_end > min(pair.info['end_frames']):
        raise HTTPException(422, 'Choose frames available in both versions.')
    if frames / pair.info['fps'] > 300:
        raise HTTPException(422, 'Choose a clip of five minutes or less.')
    if options.wipe_start + options.wipe_duration > 1.000001:
        raise HTTPException(422, 'The wipe must finish within the selected clip.')
    width, height, stacked = _geometry(pair, options)
    wipe_frames = max(2, min(frames, int(options.wipe_duration * frames + .5)))
    return {
        'kind': 'comparison_export', 'rate_n': pair.recipe['rate_n'], 'rate_d': pair.recipe['rate_d'],
        'frames': frames, 'start_frame': source_start, 'freeze': frozen, 'width': width, 'height': height,
        'mode': options.mode, 'stacked': stacked, 'swapped': options.swapped, 'artwork': artwork,
        'wipe_start': max(0, min(frames - wipe_frames, int(options.wipe_start * frames + .5))),
        'wipe_frames': wipe_frames,
    }


async def read_export_request(request: Request) -> dict:
    # Authorize first, then bound the body while reading, including chunked requests.
    enforce_rate_limit(request, '12/minute', scope='comparison-export')
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'Send export settings as JSON.')
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 3 * 1024 * 1024:
            raise HTTPException(413, 'The branding image is too large. Use a smaller logo.')
        body.extend(chunk)
    try:
        data = json.loads(body)
        if not isinstance(data, dict) or set(data) - {'options', 'artwork'}:
            raise ValueError('Invalid export')
        return data
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, 'Check the export settings, then try again.') from exc


def _artwork(encoded: str | None, recipe: dict) -> bytes | None:
    if encoded is None:
        return None
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 2 * 1024 * 1024:
            raise HTTPException(413, 'The branding image is too large. Use a smaller logo.')
        # Two transparent frames: the before and after label states. The browser
        # uses this same artwork for its preview. No user text enters an FFmpeg graph.
        with Image.open(io.BytesIO(raw), formats=['PNG']) as source:
            if source.size != (recipe['width'], recipe['height'] * 2) or getattr(source, 'n_frames', 1) != 1:
                raise ValueError('Invalid artwork dimensions')
            output = io.BytesIO()
            source.convert('RGBA').save(output, format='PNG')
            return output.getvalue()
    except (OSError, ValueError, TypeError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, 'The branding image could not be read. Choose the logo again.') from exc


def _signature(payload: str) -> str:
    return hmac.new(get_settings().SECRET_KEY.encode(), ('comparison-export:' + payload).encode(), hashlib.sha256).hexdigest()


def _export_pair(pair: Comparison, recipe: dict, receipt: str, artwork: bytes | None = None) -> Comparison:
    validate_recipe(recipe)
    paths = pair.paths if pair.info['primary_is_left'] else pair.paths[::-1]
    signatures = pair.signatures if pair.info['primary_is_left'] else pair.signatures[::-1]
    if recipe['swapped']:
        paths, signatures = paths[::-1], signatures[::-1]
    return Comparison(
        pair.key + ':export:' + hashlib.sha256(receipt.encode()).hexdigest(), paths, signatures, recipe,
        {'width': recipe['width'], 'height': recipe['height'], 'fps': pair.info['fps'], 'frame_count': recipe['frames']},
        artwork,
    )


def start_export(db, pair: Comparison, owner: str, data: dict) -> dict:
    try:
        config = ExportOptions.model_validate(data.get('options'))
    except ValidationError as exc:
        raise HTTPException(422, 'Check the export settings, then try again.') from exc
    recipe = _recipe(pair, config, data.get('artwork') is not None)
    pixels = _artwork(data.get('artwork'), recipe)
    payload = {
        'pair': hashlib.sha256(pair.key.encode()).hexdigest(),
        'owner': hashlib.sha256(owner.encode()).hexdigest(), 'recipe': recipe,
        'nonce': uuid.uuid4().hex, 'expires': int(time.time()) + 86400,
    }
    receipt = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
    exported = _export_pair(pair, recipe, receipt, pixels)
    status = comparison_status(db, exported, start=True)
    return {**status, 'token': receipt + '.' + _signature(receipt)}


def resolve_export(pair: Comparison, owner: str, token: str) -> Comparison:
    try:
        if len(token) > 4096:
            raise ValueError('Invalid receipt')
        receipt, signature = token.split('.')
        if not hmac.compare_digest(_signature(receipt), signature):
            raise ValueError('Invalid receipt')
        payload = json.loads(base64.urlsafe_b64decode(receipt + '=' * (-len(receipt) % 4)))
        if (payload['expires'] < time.time()
                or payload['pair'] != hashlib.sha256(pair.key.encode()).hexdigest()
                or payload['owner'] != hashlib.sha256(owner.encode()).hexdigest()):
            raise ValueError('Expired or changed export')
        return _export_pair(pair, payload['recipe'], receipt)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(404, 'This export is no longer available. Export it again.') from exc


def cancel_export(pair: Comparison) -> dict:
    # Serialize cancellation with the final rename. Do not remove a completed export.
    with transcode_publish_guard(pair.key, allow_cancelled=True):
        if pair.output.is_file():
            return {'status': 'complete'}
        tombstone_transcode_identity(pair.key)
    purge_transcode_identity(pair.key)
    return {'status': 'cancelled'}
