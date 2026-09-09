#!/usr/bin/env python3
"""Restricted host bridge: Unix socket on Linux, authenticated loopback on macOS."""

import argparse
import fcntl
import hashlib
import hmac
import http.server
import importlib.util
import json
import os
import plistlib
from pathlib import Path
import re
import socket
import socketserver
import shutil
import stat
import subprocess
import sys
import signal
import tempfile
import uuid


TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-alpha\.(0|[1-9][0-9]*)(?:\.dev\.(0|[1-9][0-9]*))?")
DATA_FILESYSTEMS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "apfs", "hfs"}


def mac_reserved_volumes():
    """Exclude macOS boot, recovery and other system-only APFS volumes."""
    result = subprocess.run(['diskutil', 'apfs', 'list', '-plist'], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
    return {volume['DeviceIdentifier']
            for container in plistlib.loads(result.stdout).get('Containers', [])
            for volume in container.get('Volumes', [])
            if set(volume.get('Roles', [])) - {'Data'}}


def data_folder(raw_path):
    """Validate a dedicated, empty local data folder before any installation writes."""
    if (not raw_path.startswith("/") or any(ord(c) < 32 or c in "\"'\\$#" for c in raw_path)):
        raise ValueError("Use an absolute folder path without quotes, dollar signs, backslashes or control characters.")
    requested = Path(raw_path)
    if requested.is_symlink():
        raise ValueError("Choose a real data folder, not a symbolic link.")
    path = requested.resolve()
    if any(path == temporary or temporary in path.parents for temporary in map(Path, ('/tmp', '/var/tmp', '/run', '/private/tmp', '/private/var/tmp', '/private/var/folders'))):
        raise ValueError('Choose a permanent data folder, not a temporary system directory.')
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("Choose a new or empty folder. Existing files and databases will not be overwritten.")
    parent = path
    while not parent.exists():
        parent = parent.parent
    if parent == path and os.path.ismount(parent):
        raise ValueError("Choose a folder on the drive, not the entire drive.")
    if sys.platform == "darwin":
        # /Users can be a firmlink into the writable Data volume. Asking about
        # '/' instead would incorrectly identify the read-only system volume.
        # GNU df does not resolve Apple's Data-volume firmlinks correctly.
        mounted = subprocess.run(['/bin/df', '-P', str(parent)], check=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        device = mounted.stdout.decode('utf-8').splitlines()[-1].split()[0]
        if not device.startswith('/dev/'):
            raise ValueError('Choose a local disk for the Vue database.')
        result = subprocess.run(["diskutil", "info", "-plist", device], check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        info = plistlib.loads(result.stdout)
        filesystem = info.get("FilesystemType", "").lower()
        local = info.get("WritableVolume") is True
        if info.get('DeviceIdentifier') in mac_reserved_volumes():
            raise ValueError('Choose a normal storage volume, not a macOS system or recovery volume.')
    else:
        result = subprocess.run(["findmnt", "--json", "--target", str(parent), "--output", "FSTYPE,OPTIONS"],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        info = json.loads(result.stdout)["filesystems"][0]
        filesystem = info["fstype"].lower()
        local = "ro" not in info["options"].split(",")
    if not local or filesystem not in DATA_FILESYSTEMS:
        raise ValueError("The database needs a writable local Linux or Mac filesystem. Use the internal drive or a suitable external drive. Network shares and FAT/exFAT drives can hold media, but not the Vue database. Nothing will be formatted.")
    return path


def paths_overlap(first, second):
    return first == second or first in second.parents or second in first.parents


def storage_records(home, extension="root"):
    result = []
    for record in sorted((home / "storage.d").glob(f"*.{extension}")):
        trusted_path(record)
        if record.stat().st_size > 8192:
            raise ValueError("Invalid storage record.")
        label, path, mode, sentinel = record.read_text(encoding="utf-8").splitlines()
        if mode not in {"ro", "rw"} or not re.fullmatch(r"[a-f0-9]{32,128}", sentinel):
            raise ValueError("Invalid storage record.")
        result.append(dict(label=label, path=Path(path), mode=mode, sentinel=sentinel))
    return result


def drive_marker(path):
    descriptor = None
    try:
        descriptor = os.open(path / ".vueio-storage-id", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        token = os.read(descriptor, 130).decode("ascii").rstrip("\n")
        return token if re.fullmatch(r"[a-f0-9]{32,128}", token) else None
    except (OSError, UnicodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def discover_drives(home, records):
    """Read mounted local volumes, never scan media or expose the host root.

    The browser gets a selection token, not authority to submit a host path.
    Re-enumeration at selection time rejects an unplugged/replaced volume.
    Desktop launchers must implement this same host-side boundary; mounting
    /Volumes or a Windows drive in a browser is not Docker file sharing.
    """
    if sys.platform == "darwin":
        volumes = []
        reserved = mac_reserved_volumes()
        # Only OS-mounted volumes. Do not recursively scan folders or media.
        for path in list(Path('/Volumes').iterdir())[:64]:
            if path.is_symlink() or not os.path.ismount(path):
                continue
            try:
                output = subprocess.run(["diskutil", "info", "-plist", str(path)], check=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
                info = plistlib.loads(output.stdout)
            except (OSError, ValueError, subprocess.SubprocessError):
                # A drive can disappear between enumeration and inspection.
                continue
            if info.get("MountPoint") != str(path) or info.get('DeviceIdentifier') in reserved:
                continue
            volumes.append(dict(target=str(path), source=info.get("DeviceNode", ""),
                                fstype=info.get("FilesystemType", ""), uuid=info.get("VolumeUUID", ""),
                                id=info.get("DeviceIdentifier", ""), label=info.get("VolumeName", path.name),
                                options="rw" if info.get("WritableVolume") is True else "ro"))
    else:
        output = subprocess.run(
            ["findmnt", "--json", "--list", "--real", "--output", "TARGET,SOURCE,FSTYPE,OPTIONS,UUID,LABEL,ID"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3,
        )
        volumes = json.loads(output.stdout).get("filesystems", [])
    blocked = [home, Path("/boot"), Path("/etc"), Path("/usr"), Path("/var"), Path("/proc"), Path("/sys"), Path("/dev"), Path("/root")]
    if (home / '.env').is_file():
        for line in (home / '.env').read_text(encoding='utf-8').splitlines():
            if line.startswith('VUEIO_STATE_PATH='):
                blocked.append(Path(line.partition('=')[2]))
    drives = []
    for volume in volumes:
        raw_path = volume.get("target") or ""
        if not raw_path.startswith("/") or len(raw_path) > 2048 or any(ord(char) < 32 for char in raw_path):
            continue
        path = Path(raw_path)
        if path in {Path("/"), Path("/home"), Path("/media"), Path("/mnt"), Path("/run")}:
            continue
        if (any(paths_overlap(path, entry) for entry in blocked)
                or (Path("/run") in path.parents and Path("/run/media") not in path.parents)):
            continue
        if not (str(volume.get("source", "")).startswith("/dev/") or volume.get("fstype") == "zfs"):
            continue
        if any(paths_overlap(path, record["path"]) for record in records):
            continue
        # The privileged helper must not bind a path that an ordinary local
        # user could replace with a symlink after selection. Only OS-managed
        # mount parents are eligible for the browser picker; custom paths stay
        # available through the explicit host command.
        try:
            trusted_path(path.parent)
            if path.resolve() != path:
                continue
        except (OSError, ValueError):
            continue
        if any(path in Path(other.get("target") or "/").parents for other in volumes if other is not volume):
            continue
        identity = "\0".join(str(volume.get(field) or "") for field in ("target", "source", "uuid", "id"))
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        marker = drive_marker(path)
        previous = next((record for record in records if marker and record["sentinel"] == marker), None)
        drives.append(dict(
            id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            label=volume.get("label") or path.name, path=str(path),
            read_only="ro" in str(volume.get("options", "")).split(","),
            supports_database=str(volume.get('fstype', '')).lower() in DATA_FILESYSTEMS,
            total_bytes=usage.total, free_bytes=usage.free,
            reconnect_label=previous["label"] if previous else None,
        ))
        if len(drives) == 64:
            break
    return drives


def version_key(value):
    match = TAG.fullmatch(value)
    if not match:
        raise ValueError("Invalid release version.")
    return tuple(int(part) if part is not None else -1 for part in match.groups())


def trusted_path(path):
    """Only the host administrator may replace executable code or configuration."""
    for entry in (path, *path.parents):
        info = entry.lstat()
        owners = {0, os.geteuid()} if sys.platform == 'darwin' else {0}
        if info.st_uid not in owners or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise ValueError("Updater files and their parent directories must belong to the host administrator and not be writable by other users.")


class Updater(socketserver.TCPServer):
    timeout = 1
    allow_reuse_address = True

    def __init__(self, home, controller):
        self.home = home
        self.controller = controller
        self.progress_file = home / ".update-progress.json"
        self.lock_file = home / ".maintenance.lock"
        self.child = None
        self.storage_child = None
        self.media = None
        self.storage_progress = dict(state="idle", message="Ready to connect storage.")
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
        os.chown(directory, os.geteuid(), int(gid))
        directory.chmod(0o750)
        self.access_token = None
        if sys.platform == 'darwin':
            media_file = home / 'vueio-media.py'
            if media_file.is_file():
                trusted_path(media_file)
                spec = importlib.util.spec_from_file_location('vueio_native_media', media_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.media = module.NativeMedia(self)
            # A host Unix socket cannot be shared through Docker Desktop's VM.
            # Never listen on the LAN, and never accept an unauthenticated call.
            token_path = directory / 'access-token'
            trusted_path(token_path)
            token = token_path.read_text(encoding='ascii').strip()
            if not re.fullmatch(r'[a-f0-9]{64}', token):
                raise ValueError('The Mac host helper needs a valid access token.')
            port = int(config.get('VUEIO_UPDATER_PORT', '0'))
            if not 1024 <= port <= 65535:
                raise ValueError('The Mac host helper needs a valid local port.')
            self.access_token = token
            super().__init__(('127.0.0.1', port), Handler)
            return
        self.address_family = socket.AF_UNIX
        socket_path = directory / "control.sock"
        if socket_path.exists():
            if not stat.S_ISSOCK(socket_path.lstat().st_mode):
                raise ValueError("The updater socket path is occupied by another file.")
            socket_path.unlink()
        super().__init__(str(socket_path), Handler)
        os.chown(socket_path, os.geteuid(), int(gid))
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
            result.setdefault("operation", "update")
            result.setdefault("target_channel", None)
            result["channel_switch_supported"] = True
            return result
        except FileNotFoundError:
            return dict(supported=True, state="idle", phase="complete", progress=0,
                        message="Ready to update.", version=None, previous_version=None,
                        operation_id=None, operation="update", target_channel=None,
                        channel_switch_supported=True)

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
                        result.update(operation="update", target_channel=None)
                    if result.get("operation") == "channel" and not pending.exists():
                        result.update(state="failed", phase="failed", message="The channel switch was interrupted. Try switching channels again.")
                    else:
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
                          previous_version=previous, operation_id=uuid.uuid4().hex,
                          operation="update", target_channel=None, channel_switch_supported=True)
            return self.launch_operation(lock, config, result, ["update", version])
        finally:
            lock.close()

    def storage(self):
        self.reap_child()
        if (self.home / "compose.installation.yml").exists():
            return dict(supported=False, reason="custom_mounts", drives=[], operation=self.storage_progress,
                        message="This installation uses custom storage mappings. Add drives on the host, then check again here.")
        return dict(supported=True, drives=discover_drives(self.home, storage_records(self.home)),
                    operation=self.storage_progress, message="Only drives connected to the Vueio computer appear here.")

    def start_storage(self, payload):
        self.reap_child()
        if (self.home / "compose.installation.yml").exists():
            return 409, {"message": "This installation uses custom storage mappings. Connect storage on the host."}
        lock = self.acquire_lock()
        if lock is None:
            return 409, {"message": "Another host operation is in progress. Wait for it to finish."}
        try:
            if (self.home / ".update-state").exists():
                return 409, {"message": "Finish the interrupted update on the host before changing storage."}
            config = self.config()
            action = payload.get("action")
            if action == "reconnect" and set(payload) == {"action"}:
                arguments = ["storage", "reconnect"]
            elif action == "add" and set(payload) == {"action", "id", "label", "mode"}:
                label, mode = payload["label"], payload["mode"]
                if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}", label) or not isinstance(mode, str) or mode not in {"ro", "rw"}:
                    return 400, {"message": "Use a storage name with letters, numbers, spaces, dots, dashes or underscores."}
                records = storage_records(self.home)
                normalize = lambda value: re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
                drive = next((drive for drive in discover_drives(self.home, records) if drive["id"] == payload["id"]), None)
                if drive is None:
                    return 409, {"message": "This drive is no longer available. Check for drives again."}
                if drive["reconnect_label"]:
                    label = drive["reconnect_label"]
                    previous = next(record for record in records if record["label"] == label)
                    if drive_marker(previous["path"]) == previous["sentinel"]:
                        return 409, {"message": "The original drive is still connected. Vueio will not replace it with another copy."}
                elif normalize(label) == "data" or any(normalize(record["label"]) == normalize(label) for record in records):
                    return 409, {"message": "Choose a different storage name. This name is already in use or reserved."}
                for retired in storage_records(self.home, "removed"):
                    if normalize(retired["label"]) == normalize(label) and drive_marker(Path(drive["path"])) != retired["sentinel"]:
                        return 409, {"message": "This name belongs to a disconnected drive. Use the original drive or choose a new storage name."}
                if drive["read_only"] and not drive["reconnect_label"]:
                    return 409, {"message": "Unlock this drive on the computer first. Vueio needs to save a small identity file before it can connect it."}
                data_path = Path(config.get("VUEIO_DATA_PATH", str(self.home / "data"))).resolve()
                if paths_overlap(Path(drive["path"]), data_path):
                    return 409, {"message": "Media storage must be separate from Vueio's private application data."}
                # Check as the app's user, not this privileged helper. Do not
                # recursively change ownership of someone's existing drive.
                identity = {} if sys.platform == 'darwin' else dict(user=int(config['VUEIO_PUID']), group=int(config['VUEIO_PGID']), extra_groups=[])
                access = subprocess.run(
                    [sys.executable, "-c", "import os,sys; sys.exit(0 if os.access(sys.argv[1], int(sys.argv[2])) else 1)",
                     drive["path"], str(os.R_OK | os.X_OK | (os.W_OK if mode == "rw" and not drive["reconnect_label"] else 0))],
                    **identity,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
                )
                if access.returncode:
                    return 409, {"message": "Vueio cannot access this drive with the selected permissions. Check its sharing permissions on the computer."}
                arguments = (["storage", "reconnect", label, drive["path"]] if drive["reconnect_label"]
                             else ["storage", "add", label, drive["path"], mode])
            else:
                return 400, {"message": "Select a drive and its access mode, or reconnect registered storage."}
            environment = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8",
                           "VUEIO_HOME": str(self.home), "VUEIO_NONINTERACTIVE": "1", "VUEIO_MAINTENANCE_FD": str(lock.fileno())}
            if sys.platform == 'darwin':
                environment.update({key: os.environ[key] for key in ('HOME', 'PATH') if key in os.environ})
            if action == "add":
                environment["VUEIO_STORAGE_DEVICE_ID"] = drive["id"]
            self.storage_child = subprocess.Popen(
                [str(self.controller), *arguments], env=environment, pass_fds=(lock.fileno(),),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            )
            self.storage_progress = dict(state="running", message="Connecting storage. Vueio will restart briefly; this page will reconnect.")
            return 202, self.storage_progress
        finally:
            lock.close()

    def start_channel(self, channel):
        if channel not in {"stable", "nightly"}:
            raise ValueError("Invalid update channel.")
        lock = self.acquire_lock()
        if lock is None:
            return 409, {"message": "Another host operation is in progress. Try again when it finishes."}
        try:
            progress = self.read_progress()
            if ((self.home / ".update-state").exists()
                    or (progress.get("operation") == "update" and progress.get("state") in {"running", "interrupted"})):
                return 409, {"message": "An interrupted update needs attention on the host before switching channels."}
            config = self.config()
            previous = config.get("VUEIO_VERSION", "")
            version_key(previous)
            result = dict(supported=True, state="running", phase="queued", progress=0,
                          message="Preparing to switch update channels…", version=previous,
                          previous_version=previous, operation_id=uuid.uuid4().hex,
                          operation="channel", target_channel=channel, channel_switch_supported=True)
            return self.launch_operation(lock, config, result, ["channel", channel])
        finally:
            lock.close()

    def launch_operation(self, lock, config, result, arguments):
        self.write_progress(result)
        environment = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8", "NO_COLOR": "1", "VUEIO_HOME": str(self.home),
            "VUEIO_NONINTERACTIVE": "1", "VUEIO_MAINTENANCE_FD": str(lock.fileno()),
            "VUEIO_UPDATE_OPERATION_ID": result["operation_id"],
        }
        if sys.platform == 'darwin':
            environment.update({key: os.environ[key] for key in ('HOME', 'PATH') if key in os.environ})
        if config.get("VUEIO_UPDATE_GITHUB_TOKEN"):
            environment["VUEIO_UPDATE_GITHUB_TOKEN"] = config["VUEIO_UPDATE_GITHUB_TOKEN"]
        try:
            self.child = subprocess.Popen(
                [str(self.controller), *arguments], env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                pass_fds=(lock.fileno(),), start_new_session=True,
            )
        except OSError:
            result.update(state="failed", phase="failed", message="The host could not start its maintenance command.")
            self.write_progress(result)
            return 503, result
        return 202, result

    def reap_child(self):
        if self.media is not None:
            self.media.reap()
        if self.storage_child is not None and self.storage_child.poll() is not None:
            succeeded = self.storage_child.returncode == 0
            self.storage_progress = dict(
                state="succeeded" if succeeded else "failed",
                message="Storage connections were refreshed." if succeeded else "Storage needs attention. Check the connected locations before trying again; the host command may have saved the connection.",
            )
            self.storage_child = None
        if self.child is not None and self.child.poll() is not None:
            self.child = None
            # The controller writes the terminal result. A crash leaves an
            # interrupted state; a service restart never retries the operation.
            self.status()


class Handler(http.server.BaseHTTPRequestHandler):
    def parse_request(self):
        if not super().parse_request():
            return False
        token = self.server.access_token
        if token is not None:
            supplied = self.headers.get('Authorization', '')
            if (self.headers.get('Origin') or not hmac.compare_digest(supplied.encode('utf-8'), f'Bearer {token}'.encode('ascii'))):
                self.reply(403, {'message': 'Host access denied.'})
                return False
        return True

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
        if self.path.startswith('/media/jobs/') and self.server.media is not None:
            try:
                self.reply(200, self.server.media.poll(self.path.rsplit('/', 1)[-1]))
            except (OSError, ValueError):
                self.reply(409, {'message': 'The native media job is not available.'})
            return
        if self.path not in {"/status", "/storage"}:
            self.reply(404, {"message": "Unknown updater endpoint."})
            return
        try:
            self.reply(200, self.server.storage() if self.path == "/storage" else self.server.status())
        except (OSError, ValueError, subprocess.SubprocessError):
            self.reply(503, {"message": "The host could not check its state. Check the host helper and try again."})

    def do_POST(self):
        if self.path in {'/media/check', '/media/jobs', '/media/cancel'}:
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not self.server.media or not 0 < length <= 16384 or self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid media request.')
                payload = json.loads(self.rfile.read(length))
                if self.path == '/media/check' and payload == {}:
                    result = self.server.media.check()
                elif self.path == '/media/jobs':
                    result = self.server.media.start(payload)
                elif self.path == '/media/cancel' and isinstance(payload, dict) and set(payload) == {'id'} and isinstance(payload['id'], str):
                    result = self.server.media.cancel(payload['id'])
                else:
                    raise ValueError('Invalid media request.')
                self.reply(200, result)
            except (OSError, ValueError, subprocess.SubprocessError):
                self.reply(409, {'message': 'Native media processing is unavailable. CPU processing remains available.'})
            return
        if self.path not in {"/update", "/channel", "/storage"}:
            self.reply(404, {"message": "Unknown updater endpoint."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (not 0 < length <= 256 or self.headers.get("Transfer-Encoding")
                    or self.headers.get_content_type() != "application/json"):
                raise ValueError("Invalid request.")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/storage":
                if not isinstance(payload, dict):
                    raise ValueError("Invalid storage request.")
                code, result = self.server.start_storage(payload)
                self.reply(code, result)
                return
            field = "channel" if self.path == "/channel" else "version"
            if not isinstance(payload, dict) or set(payload) != {field}:
                raise ValueError("Invalid request.")
            value = payload[field]
            if not isinstance(value, str) or len(value) > 100:
                raise ValueError("Invalid request.")
            if field == "channel":
                if value not in {"stable", "nightly"}:
                    raise ValueError("Invalid update channel.")
            elif not TAG.fullmatch(value):
                raise ValueError("Invalid release version.")
        except (ValueError, OSError, subprocess.SubprocessError):
            message = ("The drive could not be connected. Check its access permissions and try again." if self.path == "/storage"
                       else "Provide a stable or nightly channel as JSON." if self.path == "/channel"
                       else "Provide a valid release version as JSON.")
            self.reply(400, {"message": message})
            return
        try:
            code, result = self.server.start_channel(value) if field == "channel" else self.server.start_update(value)
            self.reply(code, result)
        except (OSError, ValueError):
            self.reply(503, {"message": "The host updater configuration needs attention."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--controller", type=Path)
    parser.add_argument("--list-drives", nargs='?', const='media', choices=('media', 'data'))
    parser.add_argument("--check-drive", nargs=2, metavar=("ID", "PATH"))
    parser.add_argument("--data-folder", metavar="PATH")
    arguments = parser.parse_args()
    if arguments.data_folder:
        try:
            print(data_folder(arguments.data_folder))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            parser.exit(1, f"{exc}\n")
        return
    if arguments.list_drives:
        # Read-only installer discovery runs before the installation exists.
        for drive in discover_drives(arguments.home.resolve(), []):
            if not drive["read_only"] and (arguments.list_drives != 'data' or drive['supports_database']):
                print(drive["path"])
        return
    if arguments.check_drive:
        selected_id, selected_path = arguments.check_drive
        matches = any(drive["id"] == selected_id and drive["path"] == selected_path
                      for drive in discover_drives(arguments.home.resolve(), storage_records(arguments.home)))
        sys.exit(0 if matches else 1)
    if not arguments.controller:
        parser.error("--controller is required when running the host service.")
    if os.geteuid() != 0 and sys.platform != 'darwin':
        parser.error("The host updater must run as root.")
    if sys.platform == 'darwin' and os.geteuid() == 0:
        parser.error('The Mac host helper must run as the signed-in Mac user, not root.')
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
            def stop_media(_signal, _frame):
                if server.media is not None:
                    server.media.close()
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop_media)
            signal.signal(signal.SIGINT, stop_media)
            while True:
                server.handle_request()
                server.reap_child()
                # Adopt a verified helper update after the controller finishes.
                if Path(__file__).stat().st_mtime_ns != helper_mtime:
                    lock = server.acquire_lock()
                    if lock is not None:
                        lock.close()
                        if server.media is not None:
                            server.media.close()
                        daemon_lock.close()
                        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])


if __name__ == "__main__":
    main()
