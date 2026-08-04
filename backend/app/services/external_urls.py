from __future__ import annotations

import re
from urllib.parse import urlsplit

_URL_SCHEME_RE = re.compile(r'^[a-z][a-z0-9+.-]*:', re.IGNORECASE)


def normalize_external_http_url(value: object, *, max_length: int = 500) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    candidate = raw if _URL_SCHEME_RE.match(raw) else f'https://{raw}'
    if (
        len(candidate) > max_length
        or '\\' in candidate
        or any(character.isspace() or ord(character) == 127 for character in candidate)
    ):
        return ''
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname or ''
        parsed.port
    except ValueError:
        return ''
    if (
        parsed.scheme.lower() not in {'http', 'https'}
        or not hostname
        or any(character.isspace() for character in hostname)
        or '@' in parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return ''
    return candidate


def normalize_http_origin(value: object) -> str:
    normalized = normalize_external_http_url(value)
    if not normalized:
        return ''
    parsed = urlsplit(normalized)
    if parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        return ''
    return f'{parsed.scheme.lower()}://{parsed.netloc}'.rstrip('/')
