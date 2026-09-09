from __future__ import annotations

import http.client
import json
from pathlib import Path
import re
import socket
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.auth import get_user_from_session
from app.services.external_urls import normalize_http_origin
from app.services.release_updates import get_update_status
from app.services.user_access import is_admin_user

MAX_RESPONSE_BYTES = 16 * 1024


def require_host_admin(vueio_session: str | None) -> None:
    # Host access requires an admin browser session, never an agent API key.
    user = get_user_from_session(vueio_session, allow_agent_fallback=False)
    if not user:
        raise HTTPException(status_code=401, detail='Sign in to manage this Vueio installation.')
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail='Admin access required')


def require_host_origin(request: Request) -> None:
    origin = normalize_http_origin(request.headers.get('origin'))
    allowed = {
        normalize_http_origin(get_settings().VUEIO_PUBLIC_BASE_URL),
        normalize_http_origin(f'{request.url.scheme}://{request.url.netloc}'),
    }
    fetch_site = request.headers.get('sec-fetch-site')
    if not origin or origin not in allowed or (fetch_site and fetch_site != 'same-origin'):
        raise HTTPException(status_code=403, detail='Start this action from this Vueio instance.')


class HostUpdateStatus(BaseModel):
    supported: bool = Field(strict=True)
    channel_switch_supported: bool = Field(default=False, strict=True)
    operation: Literal['update', 'channel'] = 'update'
    target_channel: Literal['stable', 'nightly'] | None = None
    state: Literal['idle', 'running', 'succeeded', 'failed', 'interrupted']
    phase: Literal[
        'idle', 'queued', 'preflight', 'assets', 'images', 'backup', 'install',
        'restart', 'health', 'recovery', 'complete', 'failed',
    ]
    progress: int = Field(strict=True, ge=0, le=100)
    message: str = Field(max_length=500)
    version: str | None = Field(default=None, max_length=100)
    previous_version: str | None = Field(default=None, max_length=100)
    operation_id: str | None = Field(default=None, max_length=100)


class _HostConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str):
        super().__init__('localhost', timeout=5)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def host_request_json(method: str, path: str, payload: dict | None = None, *, max_bytes: int = MAX_RESPONSE_BYTES, timeout: float = 5) -> dict:
    settings = get_settings()
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if settings.VUEIO_UPDATER_URL:
        # Mac Docker Desktop only. Never accept a browser-supplied destination,
        # arbitrary host URL, redirect, or a connection without its private key.
        match = re.fullmatch(r'http://host\.docker\.internal:([0-9]{4,5})', settings.VUEIO_UPDATER_URL)
        if not match or not 1024 <= int(match[1]) <= 65535:
            raise HTTPException(status_code=503, detail='The Mac host connection needs attention.')
        try:
            with Path(settings.VUEIO_UPDATER_TOKEN_FILE).open(encoding='ascii') as handle:
                token = handle.read(66).strip()
            if not re.fullmatch(r'[a-f0-9]{64}', token):
                raise ValueError('Invalid host token')
        except (OSError, ValueError):
            raise HTTPException(status_code=503, detail='The Mac host connection needs attention.') from None
        headers['Authorization'] = f'Bearer {token}'
        connection = http.client.HTTPConnection('host.docker.internal', int(match[1]), timeout=timeout)
    else:
        socket_path = settings.VUEIO_UPDATER_SOCKET.strip()
        if not socket_path.startswith('/'):
            raise HTTPException(status_code=503, detail='The host helper needs a one-time setup on the Vueio computer.')
        connection = _HostConnection(socket_path)
    try:
        connection.request(
            method, path,
            body=json.dumps(payload) if payload is not None else None,
            headers=headers,
        )
        response = connection.getresponse()
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError('Updater response too large')
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError('Invalid host response')
        if response.status in {400, 409}:
            message = result.get('message')
            raise HTTPException(status_code=response.status, detail=(
                message if isinstance(message, str) and len(message) <= 500
                else 'Another host operation is in progress or needs attention. Refresh its status.'
            ))
        if response.status not in {200, 202}:
            raise ValueError('Updater rejected the request')
        return result
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise HTTPException(
            status_code=503,
            detail='The host helper is unavailable. Check its service on the Vueio computer, then try again.',
        ) from exc
    finally:
        connection.close()


def _host_request(method: str, path: str, payload: dict | None = None) -> dict:
    try:
        return HostUpdateStatus.model_validate(host_request_json(method, path, payload)).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail='The host updater returned an invalid status.') from exc


def get_host_update_status() -> dict:
    try:
        return _host_request('GET', '/status')
    except HTTPException as exc:
        return HostUpdateStatus(
            supported=False, state='idle', phase='idle', progress=0,
            message=exc.detail,
        ).model_dump()


def start_host_update(version: str) -> dict:
    current = get_host_update_status()
    if not current['supported']:
        raise HTTPException(status_code=503, detail=current['message'])
    if current['state'] == 'running':
        if current['operation'] == 'update' and current['version'] == version:
            return current
        raise HTTPException(status_code=409, detail='Another update is already in progress.')
    if current['state'] == 'interrupted':
        raise HTTPException(
            status_code=409,
            detail='The previous update was interrupted. Recover it on the Vueio host before starting another update.',
        )

    release = get_update_status(force_refresh=True)
    if release['status'] in {'error', 'unavailable', 'checking'}:
        raise HTTPException(status_code=503, detail='The release could not be verified. Check again before updating.')
    if not release['update_available'] or release['latest_version'] != version:
        raise HTTPException(status_code=409, detail='The available release has changed. Check again before updating.')
    return _host_request('POST', '/update', {'version': version})


def switch_host_channel(channel: Literal['stable', 'nightly']) -> dict:
    current = get_host_update_status()
    if not current['supported']:
        raise HTTPException(status_code=503, detail=current['message'])
    if not current['channel_switch_supported']:
        raise HTTPException(status_code=409, detail='Install the latest release to switch channels here.')
    if current['state'] == 'running':
        if current['operation'] == 'channel' and current['target_channel'] == channel:
            return current
        raise HTTPException(status_code=409, detail='Another host operation is already in progress.')
    if current['state'] == 'interrupted':
        raise HTTPException(status_code=409, detail='Recover the interrupted update before changing channels.')
    return _host_request('POST', '/channel', {'channel': channel})
