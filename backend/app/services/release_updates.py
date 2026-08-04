from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

from app.config import get_settings

ALPHA_TAG = re.compile(
    r'^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-alpha\.(0|[1-9]\d*)$'
)
REPOSITORY = re.compile(
    r'^[A-Za-z0-9][A-Za-z0-9.-]*/[A-Za-z0-9][A-Za-z0-9._-]*$'
)
CHECK_TTL_SECONDS = 15 * 60
MAX_RESPONSE_BYTES = 1024 * 1024

_cache: dict = {}
_cache_lock = threading.Lock()


def parse_alpha_version(tag: str) -> tuple[int, int, int, int] | None:
    match = ALPHA_TAG.fullmatch((tag or '').strip())
    return tuple(map(int, match.groups())) if match else None


def _base_status(current_version: str, repository: str) -> dict:
    configured = bool(
        REPOSITORY.fullmatch(repository)
        and not repository.lower().startswith('your-owner/')
    )
    return {
        'current_version': current_version,
        'latest_version': None,
        'update_available': False,
        'configured': configured,
        'status': 'unavailable' if not configured else 'checking',
        'release_url': '',
        'update_command': '',
        'published_at': None,
        'checked_at': None,
    }


def _fetch_releases(repository: str, token: str = '') -> list[dict]:
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Vueio-update-check',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urllib.request.Request(
        f'https://api.github.com/repos/{repository}/releases?per_page=20',
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError('release response too large')
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError('invalid release response')
    return data


def get_update_status(*, force_refresh: bool = False) -> dict:
    settings = get_settings()
    current_version = (settings.VUEIO_VERSION or 'development').strip()
    repository = (settings.VUEIO_UPDATE_REPOSITORY or '').strip()
    token = (settings.VUEIO_UPDATE_GITHUB_TOKEN or '').strip()
    result = _base_status(current_version, repository)
    if not result['configured']:
        return result

    cache_key = (repository, current_version, bool(token))
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if not force_refresh and cached and now - cached['stored_at'] < CHECK_TTL_SECONDS:
            return cached['value'].copy()

        try:
            releases = _fetch_releases(repository, token)
            candidates = [
                (parse_alpha_version(str(release.get('tag_name') or '')), release)
                for release in releases
                if isinstance(release, dict) and not release.get('draft')
            ]
            candidates = [candidate for candidate in candidates if candidate[0] is not None]
            checked_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            result['checked_at'] = checked_at
            if not candidates:
                result['status'] = 'current' if parse_alpha_version(current_version) else 'development'
            else:
                _, latest_release = max(candidates, key=lambda candidate: candidate[0])
                latest_version = str(latest_release['tag_name'])
                current_parsed = parse_alpha_version(current_version)
                latest_parsed = parse_alpha_version(latest_version)
                update_available = bool(current_parsed and latest_parsed > current_parsed)
                result.update({
                    'latest_version': latest_version,
                    'update_available': update_available,
                    'status': (
                        'development' if current_parsed is None
                        else 'available' if update_available
                        else 'current'
                    ),
                    'release_url': (
                        f'https://github.com/{repository}/releases/tag/'
                        f'{quote(latest_version, safe="")}'
                    ),
                    'update_command': (
                        f'sudo vueioctl update {latest_version}'
                        if update_available else ''
                    ),
                    'published_at': latest_release.get('published_at'),
                })
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
            result['status'] = 'error'

        _cache[cache_key] = {'stored_at': now, 'value': result.copy()}
        return result
