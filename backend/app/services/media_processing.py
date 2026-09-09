"""Processing preference and execution, with CPU as the unchanged default."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.config import get_settings
from app.services.host_updates import host_request_json
from app.services.media_encoding import build_command, hardware_devices, check_device

_lock = threading.RLock()
_devices = None
_checked_at = None
_activity = deque(maxlen=12)
_checking = False


def preferences():
    try:
        path = get_settings().DATA_DIR / 'media-processing.json'
        if path.stat().st_size > 4096:
            raise ValueError('Invalid processing settings.')
        data = json.loads(path.read_text())
        if data.get('mode') in {'cpu', 'gpu'} and isinstance(data.get('device'), str):
            return {'mode': data['mode'], 'device': data['device']}
    except (OSError, ValueError, AttributeError):
        pass
    return {'mode': 'cpu', 'device': ''}


def processing_status():
    with _lock:
        return {**preferences(), 'devices': _devices or [], 'checked_at': _checked_at, 'checking': _checking,
                'activity': list(_activity), 'native_mac': bool(get_settings().VUEIO_UPDATER_URL)}


def verify_hardware():
    global _devices, _checked_at, _checking
    with _lock:
        if _checking:
            raise HTTPException(409, 'A hardware check is already running.')
        _checking = True
    try:
        if get_settings().VUEIO_UPDATER_URL:
            result = host_request_json('POST', '/media/check', {}, timeout=45)
            devices = result.get('devices', [])
        else:
            devices = [check_device(device) for device in hardware_devices()]
        if not isinstance(devices, list) or len(devices) > 16:
            raise ValueError('Invalid hardware status.')
        for device in devices:
            if not isinstance(device, dict) or any(not isinstance(device.get(key), str) for key in ('id', 'name', 'encoder', 'message')) or any(type(device.get(key)) is not bool for key in ('encoding', 'thumbnails')):
                raise ValueError('Invalid hardware result.')
        with _lock:
            _devices, _checked_at = devices, time.time()
    except Exception:
        with _lock:
            _devices, _checked_at = [], None
        raise
    finally:
        with _lock:
            _checking = False
    return processing_status()


def save_preferences(mode, device):
    with _lock:
        if mode == 'gpu' and not any(item['id'] == device and item['encoding'] for item in (_devices or [])):
            raise HTTPException(409, 'Check the hardware and select a working GPU first.')
        path = get_settings().DATA_DIR / 'media-processing.json'
        temporary = path.with_name(f'.media-processing.{uuid4().hex}.tmp')
        try:
            with temporary.open('x') as handle:
                os.chmod(temporary, 0o600)
                json.dump({'mode': mode, 'device': device if mode == 'gpu' else ''}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return processing_status()


class RemoteProcess:
    def __init__(self, source, target, recipe):
        self.identity = uuid4().hex
        self.target = Path(target)
        self.staging = self.target.with_name(f'{self.target.stem}.{self.identity}.part{self.target.suffix}')
        if recipe['kind'] == 'hls':
            self.staging.mkdir()
        self.returncode = None
        self.stdout = self
        try:
            host_request_json('POST', '/media/jobs', {'id': self.identity, 'input': str(source), 'output': str(self.staging), 'recipe': recipe}, timeout=30)
        except Exception:
            # An uncertain response must never share an output with the CPU retry.
            try: self.terminate()
            except Exception: pass
            raise

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        result = host_request_json('GET', '/media/jobs/' + self.identity, timeout=30)
        self.returncode = result['returncode']
        self.time_us = result.get('time_us', 0)
        return self.returncode

    def __iter__(self):
        while self.poll() is None:
            yield f'out_time_ms={self.time_us}\n'
            time.sleep(.5)

    def wait(self, timeout=None):
        deadline = time.monotonic() + timeout if timeout is not None else None
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('native-media', timeout)
            time.sleep(.1)
        if self.returncode == 0 and self.staging.exists():
            if self.target.is_dir(): self.target.rmdir()
            self.staging.replace(self.target)
        elif self.returncode != 0:
            self._cleanup()
        return self.returncode

    def terminate(self):
        host_request_json('POST', '/media/cancel', {'id': self.identity}, timeout=5)
        self.returncode = -15
        self._cleanup()

    def _cleanup(self):
        if self.staging.is_dir():
            for path in self.staging.iterdir(): path.unlink()
            self.staging.rmdir()
        else:
            self.staging.unlink(missing_ok=True)

    kill = terminate


class MediaProcess:
    """Popen-shaped adapter so existing leases, progress and cancellation stay in charge."""
    def __init__(self, source, target, recipe):
        self.source, self.target, self.recipe = source, Path(target), recipe
        self.cancelled = False
        self.guard = threading.RLock()
        self.process = None
        self.returncode = None
        self.stdout = self
        pref = preferences()
        # Do not probe at CPU startup. Explicit GPU users are rechecked after restart.
        if pref['mode'] == 'gpu' and _devices is None:
            try: verify_hardware()
            except Exception: pass
        self.device = next((item for item in (_devices or []) if item['id'] == pref['device'] and item['encoding']), None) if pref['mode'] == 'gpu' else None
        if recipe['kind'] == 'thumbnail' and self.device and not self.device['thumbnails']:
            self.device = None
        self.entry = {'id': uuid4().hex, 'kind': recipe['kind'], 'processor': 'cpu', 'device': 'CPU', 'state': 'running', 'fallback': pref['mode'] == 'gpu' and not self.device, 'started_at': time.time()}
        with _lock: _activity.appendleft(self.entry)
        try:
            self._start()
        except Exception:
            if not self.device:
                self.entry['state'] = 'failed'
                raise
            self._fallback()

    def _start(self):
        if self.device and get_settings().VUEIO_UPDATER_URL:
            self.process = RemoteProcess(self.source, self.target, self.recipe)
        else:
            self.process = subprocess.Popen(build_command(self.source, self.target, self.recipe, self.device),
                                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.entry.update(processor='gpu' if self.device else 'cpu', device=self.device['name'] if self.device else 'CPU')

    def _fallback(self):
        with self.guard:
            if self.cancelled:
                return
            self.device = None
            self.entry['fallback'] = True
            if self.target.is_dir():
                # Only this attempt's private staging directory, never a published cache.
                for path in self.target.iterdir():
                    if path.is_file() or path.is_symlink(): path.unlink()
            else:
                self.target.unlink(missing_ok=True)
            try:
                self._start()
            except Exception:
                self.entry['state'] = 'failed'
                raise

    def __iter__(self):
        while True:
            try:
                yield from self.process.stdout
                code = self.process.wait()
            except Exception:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    if isinstance(self.process, subprocess.Popen):
                        self.process.kill()
                        self.process.wait()
                code = 1
            if code != 0 and self.device and not self.cancelled:
                self._fallback()
                yield 'out_time_ms=0\n'
                continue
            self.returncode = code
            self.entry['state'] = 'cancelled' if self.cancelled else ('complete' if code == 0 else 'failed')
            break

    def poll(self):
        return self.returncode if self.returncode is not None else self.process.poll()

    def wait(self, timeout=None):
        return self.returncode if self.returncode is not None else self.process.wait(timeout=timeout)

    def terminate(self):
        with self.guard:
            self.cancelled = True
            self.entry['state'] = 'cancelled'
            self.process.terminate()

    def kill(self):
        with self.guard:
            self.cancelled = True
            self.entry['state'] = 'cancelled'
            self.process.kill()


def render_thumbnail(source, output, *, width, seek):
    process = MediaProcess(source, output, {'kind': 'thumbnail', 'width': width, 'seek': seek})
    def stop():
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try: process.kill()
            except Exception: pass
    timer = threading.Timer(30, stop)
    timer.daemon = True
    timer.start()
    try:
        for _line in process.stdout:
            pass
        return process.wait() == 0 and not process.cancelled
    finally:
        timer.cancel()
