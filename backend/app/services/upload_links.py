"""Upload links: an agent sends a file from its own computer as a shot version.

version_upload opens a resumable project upload. Its signed credential travels
in a header, never a URL or request log. The upload record binds the item to a
person, agent and shot. The routes recheck access on every request.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import shlex
import time

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AgentApiKey
from app.services.external_urls import normalize_http_origin

UPLOAD_LINK_TTL_SECONDS = 24 * 60 * 60
# A Cloudflare tunnel in front of many installs refuses bodies over 100 MB.
UPLOAD_LINK_CHUNK_SIZE = 50 * 1024 * 1024
_TOKEN_VERSION = 'v2'
_CONTENT_RANGE = re.compile(r'^bytes (\d+)-(\d+)/(\d+)$')
_INVALID_LINK = 'This upload link is not valid'


def _signature(encoded_payload: str) -> bytes:
    message = f'upload-link.{_TOKEN_VERSION}.{encoded_payload}'.encode('utf-8')
    return hmac.new(get_settings().SECRET_KEY.encode(), message, hashlib.sha256).hexdigest().encode('ascii')


def issue_upload_link_token(
    *,
    item_id: str,
) -> tuple[str, int]:
    expires_at = int(time.time()) + UPLOAD_LINK_TTL_SECONDS
    payload = {
        'item_id': item_id,
        'expires_at': expires_at,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    encoded = base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')
    return f'{_TOKEN_VERSION}.{encoded}.{_signature(encoded).decode("ascii")}', expires_at


def read_upload_link_token(token: str) -> dict:
    """Return the signed fields of a link. A changed or expired link is refused."""
    version, _, rest = (token or '').partition('.')
    encoded, _, signature = rest.partition('.')
    if version != _TOKEN_VERSION or not encoded or not hmac.compare_digest(signature.encode('utf-8'), _signature(encoded)):
        raise HTTPException(status_code=403, detail=_INVALID_LINK)
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=_INVALID_LINK) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=403, detail=_INVALID_LINK)
    if int(payload.get('expires_at') or 0) < time.time():
        raise HTTPException(status_code=410, detail='This upload link expired. Start a new upload with version_upload')
    return payload


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    match = _CONTENT_RANGE.match((value or '').strip())
    if not match:
        raise HTTPException(status_code=400, detail='Send a Content-Range header: bytes start-end/total')
    start, end, total = (int(part) for part in match.groups())
    if end < start or end >= total:
        raise HTTPException(status_code=400, detail='The Content-Range header is not valid')
    return start, end, total


def bound_agent_identity(db: Session, key_id: str | None, user_id: str) -> dict | None:
    """Return the agent a link was made for, as the request middleware reads it.

    A link stops working when that agent's access is removed.
    """
    if not key_id:
        return None
    name = None
    if key_id.startswith('oauth:'):
        from app.models import OAuthGrant

        grant = db.get(OAuthGrant, key_id.removeprefix('oauth:'))
        if grant is not None and grant.revoked_at is None and grant.user_id == user_id:
            name = grant.client_name
    else:
        record = db.get(AgentApiKey, key_id)
        if record is not None and record.is_active and record.user_id == user_id:
            name = record.name
    if name is None:
        raise HTTPException(status_code=403, detail='The agent access that made this upload link was removed')
    return {'key_id': key_id, 'name': name, 'user_id': user_id}


def request_origin(request: Request) -> str:
    """The configured public address of Vue.io, or the address this request came to."""
    configured = normalize_http_origin(get_settings().VUEIO_PUBLIC_BASE_URL)
    if configured:
        return configured
    proto = (request.headers.get('x-forwarded-proto') or request.url.scheme).split(',')[0].strip()
    host = (request.headers.get('x-forwarded-host') or request.headers.get('host') or request.url.netloc).split(',')[0].strip()
    return normalize_http_origin(f'{proto}://{host}')


def upload_link_command(url: str, token: str, size: int) -> str:
    """A POSIX shell command (bash or zsh, Linux or macOS) that sends FILE to a link in chunks.

    It stops at the first error and prints the last response.
    """
    return '\n'.join([
        'FILE=/path/to/file',
        f'URL={shlex.quote(url)}',
        f'UPLOAD_TOKEN={shlex.quote(token)}',
        '(',
        f'  CHUNK={UPLOAD_LINK_CHUNK_SIZE}',
        '  [ -f "$FILE" ] || { echo "No file at $FILE" >&2; exit 1; }',
        '  SIZE=$(($(wc -c < "$FILE")))',
        f'  [ "$SIZE" -eq {int(size)} ] || {{ echo "$FILE has $SIZE bytes. This upload is for {int(size)} bytes." >&2; exit 1; }}',
        '  OUT=$(mktemp) || exit 1',
        '  trap \'rm -f "$OUT"\' EXIT',
        '  curl -fsS -H "X-Vueio-Upload-Token: $UPLOAD_TOKEN" "$URL" -o "$OUT" || exit 1',
        '  START=$(sed -n \'s/.*"received": *\\([0-9][0-9]*\\).*/\\1/p\' "$OUT")',
        '  [ -n "$START" ] || { cat "$OUT" >&2; exit 1; }',
        '  while [ "$START" -lt "$SIZE" ]; do',
        '    END=$((START + CHUNK - 1))',
        '    [ "$END" -lt "$SIZE" ] || END=$((SIZE - 1))',
        '    CODE=$(tail -c +$((START + 1)) "$FILE" | head -c $((END - START + 1)) | curl -sS -X PUT'
        ' -H "X-Vueio-Upload-Token: $UPLOAD_TOKEN" -H "Content-Range: bytes $START-$END/$SIZE" -H "Content-Type: application/octet-stream"'
        ' --data-binary @- -o "$OUT" -w "%{http_code}" "$URL")',
        '    if [ "$CODE" != 200 ]; then cat "$OUT" >&2; echo "Run this command again to resume." >&2; exit 1; fi',
        '    START=$((END + 1))',
        '  done',
        '  curl -fsS -X POST -H "X-Vueio-Upload-Token: $UPLOAD_TOKEN" "$URL" || exit 1',
        '  echo',
        ')',
    ])
