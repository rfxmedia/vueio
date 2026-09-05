#!/usr/bin/env python3
"""Restricted host update bridge. Never expose this Unix socket over TCP."""

import argparse
import fcntl
import http.server
import json
import os
from pathlib import Path
import re
import socketserver
import stat
import subprocess
import sys
import tempfile
import uuid


TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-alpha\.(0|[1-9][0-9]*)(?:\.dev\.(0|[1-9][0-9]*))?")


def version_key(value):
    match = TAG.fullmatch(value)
    if not match:
        raise ValueError("Invalid release version.")
    return tuple(int(part) if part is not None else -1 for part in match.groups())


def trusted_path(path):
    """Only the host administrator may replace executable code or configuration."""
    for entry in (path, *path.parents):
        info = entry.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise ValueError("Updater files and their parent directories must be owned by root and not writable by other users.")


class Updater(socketserver.UnixStreamServer):
    timeout = 1

    def __init__(self, home, controller):
        self.home = home
        self.controller = controller
        self.progress_file = home / ".update-progress.json"
        self.lock_file = home / ".maintenance.lock"
        self.child = None
        trusted_path(home)
        trusted_path(controller)
        trusted_path(Path(__file__).resolve())
        config = self.config()
        gid = config.get("VUEIO_PGID", "")
        if not gid.isdecimal() or int(gid) > 2**31 - 1:
            raise ValueError("The installation needs a valid engine group ID.")
        directory = home / "updater"
        directory.mkdir(mode=0o750, exist_ok=True)
        trusted_path(directory)
        os.chown(directory, 0, int(gid))
        directory.chmod(0o750)
        socket_path = directory / "control.sock"
        if socket_path.exists():
            if not stat.S_ISSOCK(socket_path.lstat().st_mode):
                raise ValueError("The updater socket path is occupied by another file.")
            socket_path.unlink()
        super().__init__(str(socket_path), Handler)
        os.chown(socket_path, 0, int(gid))
        socket_path.chmod(0o660)

    def config(self):
        path = self.home / ".env"
        trusted_path(path)
        if not (self.home / "compose.yml").is_file() or not (self.home / "compose.storage.yml").is_file():
            raise ValueError("This host does not have a managed Vueio installation.")
        values = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and not line.startswith("#"):
                values[key] = value
        return values

    def acquire_lock(self):
        handle = self.lock_file.open("a")
        os.chmod(self.lock_file, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle

    def read_progress(self):
        try:
            if self.progress_file.stat().st_size > 4096:
                raise ValueError("Invalid update state.")
            result = json.loads(self.progress_file.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError("Invalid update state.")
            return result
        except FileNotFoundError:
            return dict(supported=True, state="idle", phase="complete", progress=0,
                        message="Ready to update.", version=None, previous_version=None,
                        operation_id=None)

    def write_progress(self, result):
        descriptor, temporary = tempfile.mkstemp(prefix=".update-progress.", dir=self.home)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(result, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.progress_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def status(self):
        result = self.read_progress()
        lock = self.acquire_lock()
        if lock is not None:
            try:
                result = self.read_progress()
                pending = self.home / ".update-state"
                if result.get("state") == "running" or (pending.exists() and result.get("state") != "interrupted"):
                    if pending.exists():
                        if pending.stat().st_size > 8192:
                            raise ValueError("Invalid pending update state.")
                        values = dict(line.split("=", 1) for line in pending.read_text(encoding="utf-8").splitlines() if "=" in line)
                        for field, key in (("version", "requested_version"), ("previous_version", "previous_version")):
                            if TAG.fullmatch(values.get(key, "")):
                                result[field] = values[key]
                    result.update(state="interrupted", message="The update needs attention on the host before another update can start.")
                    self.write_progress(result)
            finally:
                lock.close()
        return result

    def start_update(self, version):
        lock = self.acquire_lock()
        if lock is None:
            return 409, {"message": "Another host operation is in progress. Try again when it finishes."}
        try:
            config = self.config()
            previous = config.get("VUEIO_VERSION", "")
            channel = config.get("VUEIO_CHANNEL", "stable")
            if channel not in {"nightly", "stable"}:
                return 503, {"message": "The host update channel is not configured."}
            if version_key(version) <= version_key(previous):
                return 409, {"message": "This release is already installed or older than the installed version."}
            if channel == "stable" and ".dev." in version:
                return 409, {"message": "The host follows Stable and cannot install a Nightly release."}
            if (self.home / ".update-state").exists():
                return 409, {"message": "An interrupted update needs attention on the host before another update can start."}
            result = dict(supported=True, state="running", phase="queued", progress=0,
                          message="Preparing the update…", version=version,
                          previous_version=previous, operation_id=uuid.uuid4().hex)
            self.write_progress(result)
            environment = {
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C.UTF-8", "NO_COLOR": "1", "VUEIO_HOME": str(self.home),
                "VUEIO_NONINTERACTIVE": "1", "VUEIO_MAINTENANCE_FD": str(lock.fileno()),
                "VUEIO_UPDATE_OPERATION_ID": result["operation_id"],
            }
            if config.get("VUEIO_UPDATE_GITHUB_TOKEN"):
                environment["VUEIO_UPDATE_GITHUB_TOKEN"] = config["VUEIO_UPDATE_GITHUB_TOKEN"]
            try:
                self.child = subprocess.Popen(
                    [str(self.controller), "update", version], env=environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    pass_fds=(lock.fileno(),), start_new_session=True,
                )
            except OSError:
                result.update(state="failed", phase="failed", message="The host could not start its update command.")
                self.write_progress(result)
                return 503, result
            return 202, result
        finally:
            lock.close()

    def reap_child(self):
        if self.child is not None and self.child.poll() is not None:
            self.child = None
            # The controller writes the terminal result. A crash leaves an
            # interrupted state; a service restart never retries the operation.
            self.status()


class Handler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def log_message(self, *_args):
        pass

    def reply(self, code, result):
        body = json.dumps(result).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/status":
            self.reply(404, {"message": "Unknown updater endpoint."})
            return
        try:
            self.reply(200, self.server.status())
        except (OSError, ValueError):
            self.reply(503, {"message": "The host update state needs attention."})

    def do_POST(self):
        if self.path != "/update":
            self.reply(404, {"message": "Unknown updater endpoint."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (not 0 < length <= 256 or self.headers.get("Transfer-Encoding")
                    or self.headers.get_content_type() != "application/json"):
                raise ValueError("Invalid request.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or set(payload) != {"version"}:
                raise ValueError("Invalid request.")
            version = payload["version"]
            if not isinstance(version, str) or len(version) > 100 or not TAG.fullmatch(version):
                raise ValueError("Invalid release version.")
        except (ValueError, OSError):
            self.reply(400, {"message": "Provide a valid release version as JSON."})
            return
        try:
            code, result = self.server.start_update(version)
            self.reply(code, result)
        except (OSError, ValueError):
            self.reply(503, {"message": "The host updater configuration needs attention."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--controller", type=Path, required=True)
    arguments = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("The host updater must run as root.")
    home = arguments.home.resolve()
    if home == Path("/"):
        parser.error("The installation directory cannot be the host root.")
    controller = arguments.controller.resolve()
    # A separate daemon lock prevents replacing a live daemon's socket.
    trusted_path(home)
    with (home / ".updater-service.lock").open("a") as daemon_lock:
        try:
            fcntl.flock(daemon_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("The host updater is already running.")
        helper_mtime = Path(__file__).stat().st_mtime_ns
        with Updater(home, controller) as server:
            while True:
                server.handle_request()
                server.reap_child()
                # Adopt a verified helper update after the controller finishes.
                if Path(__file__).stat().st_mtime_ns != helper_mtime:
                    lock = server.acquire_lock()
                    if lock is not None:
                        lock.close()
                        daemon_lock.close()
                        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])


if __name__ == "__main__":
    main()
