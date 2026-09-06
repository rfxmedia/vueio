from __future__ import annotations

import http.client
import json
import socket
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.release_updates import get_update_status

MAX_RESPONSE_BYTES = 16 * 1024


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


def _host_request(method: str, path: str, payload: dict | None = None) -> dict:
    socket_path = get_settings().VUEIO_UPDATER_SOCKET.strip()
    if not socket_path.startswith('/'):
        raise HTTPException(status_code=503, detail='One-click updates need a one-time setup on the Vueio host.')
    connection = _HostConnection(socket_path)
    try:
        connection.request(
            method, path,
            body=json.dumps(payload) if payload is not None else None,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        )
        response = connection.getresponse()
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError('Updater response too large')
        if response.status == 409:
            raise HTTPException(status_code=409, detail='Another host operation is in progress or needs attention. Refresh its status.')
        if response.status not in {200, 202}:
            raise ValueError('Updater rejected the request')
        return HostUpdateStatus.model_validate(json.loads(body)).model_dump()
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise HTTPException(
            status_code=503,
            detail='The host updater is unavailable. Check its service on the Vueio host, then try again.',
        ) from exc
    finally:
        connection.close()


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
