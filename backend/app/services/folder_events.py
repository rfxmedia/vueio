from __future__ import annotations

import asyncio
import ctypes
import os
import re
import stat
import struct
from dataclasses import dataclass, field
from pathlib import Path


POLL_SECONDS = 4
RECONCILE_SECONDS = 30
COALESCE_SECONDS = 0.5
MAX_SUBSCRIPTIONS = 256
MAX_DIRECTORIES = 4096
MAX_FALLBACK_DIRECTORIES = 256

_CLOSE_WRITE = 0x00000008
_MOVED_FROM = 0x00000040
_MOVED_TO = 0x00000080
_CREATE = 0x00000100
_DELETE = 0x00000200
_DELETE_SELF = 0x00000400
_MOVE_SELF = 0x00000800
_UNMOUNT = 0x00002000
_OVERFLOW = 0x00004000
_IGNORED = 0x00008000
_ISDIR = 0x40000000
_WATCH_MASK = _CLOSE_WRITE | _MOVED_FROM | _MOVED_TO | _CREATE | _DELETE | _DELETE_SELF | _MOVE_SELF
_EVENT = struct.Struct('iIII')


@dataclass(frozen=True)
class FolderBinding:
    directory: Path
    virtual_path: str
    names: frozenset[str] | None = None
    excluded_names: frozenset[str] = frozenset()

    def accepts(self, name: str | None) -> bool:
        if name is None:
            return True
        if self.names is not None:
            return name in self.names
        return not name.startswith('.') and name not in self.excluded_names


@dataclass(eq=False)
class FolderSubscription:
    owner: str
    bindings: tuple[FolderBinding, ...] = ()
    dirty: set[str] = field(default_factory=set)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    timer: asyncio.TimerHandle | None = None

    def mark(self, path: str) -> None:
        self.dirty.add(path)
        if self.timer is None:
            self.timer = asyncio.get_running_loop().call_later(COALESCE_SECONDS, self._ready)

    def _ready(self) -> None:
        self.timer = None
        self.changed.set()

    def take_changes(self) -> list[str]:
        paths = sorted(self.dirty)
        self.dirty.clear()
        self.changed.clear()
        return paths


@dataclass
class _Directory:
    path: Path
    listeners: dict[FolderSubscription, tuple[FolderBinding, ...]] = field(default_factory=dict)
    descriptor: int | None = None
    previous: dict | None = None
    published: dict | None = None
    initialized: asyncio.Event = field(default_factory=asyncio.Event)
    signature: tuple | None = None
    pending: set[str] = field(default_factory=set)
    snapshot_bindings: tuple[FolderBinding, ...] = ()
    last_full_scan: float = 0

    def notify(self, name: str | None = None) -> None:
        for subscription, bindings in self.listeners.items():
            for binding in bindings:
                if binding.accepts(name):
                    subscription.mark(binding.virtual_path)


def _remote_mounts() -> tuple[Path, ...]:
    try:
        lines = Path('/proc/self/mountinfo').read_text().splitlines()
    except OSError:
        return ()
    mounts = []
    for line in lines:
        fields = line.split()
        separator = fields.index('-')
        filesystem = fields[separator + 1]
        if filesystem in {'nfs', 'nfs4', 'cifs', 'smb3', '9p', 'ceph'} or filesystem.startswith('fuse'):
            mount = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), fields[4])
            mounts.append(Path(mount))
    return tuple(mounts)


def _directory_snapshot(path: Path, bindings: tuple[FolderBinding, ...]) -> dict | None:
    """Read shallow metadata only, on filesystems that cannot send events."""
    try:
        result = {}
        broad = tuple(binding for binding in bindings if binding.names is None)
        names = frozenset(name for binding in bindings for name in (binding.names or ()))
        if not broad:
            # Watching one linked source file must not enumerate or stat its
            # potentially large, otherwise unrelated network directory.
            for name in names:
                try:
                    info = (path / name).lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISLNK(info.st_mode):
                    result[name] = (info.st_mode, info.st_ino, info.st_size, info.st_mtime_ns)
            return result
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.name not in names and not any(binding.accepts(entry.name) for binding in broad):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat.S_ISLNK(info.st_mode):
                    continue
                result[entry.name] = (info.st_mode, info.st_ino, info.st_size, info.st_mtime_ns)
        return result
    except OSError:
        return None


def _fallback_snapshot(path: Path, bindings: tuple[FolderBinding, ...], signature: tuple | None, pending: frozenset[str], reconcile: bool) -> tuple:
    try:
        info = path.stat()
        current_signature = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
    except OSError:
        return None, None, True
    complete = reconcile or current_signature != signature
    if complete:
        return current_signature, _directory_snapshot(path, bindings), True
    # Directory timestamps do not change during an existing file write. Check
    # pending/new files directly; reconcile older entries at a slower interval.
    current = _directory_snapshot(path, (FolderBinding(path, '', pending),)) if pending else {}
    return current_signature, current, False


class FolderEventHub:
    """Share nonrecursive directory watches between visible browser folders."""

    def __init__(self) -> None:
        self.directories: dict[Path, _Directory] = {}
        self.subscriptions: set[FolderSubscription] = set()
        self._descriptors: dict[int, set[Path]] = {}
        self._fd: int | None = None
        self._libc = None
        self._started = False
        self._remote: tuple[Path, ...] = ()
        self._poll_task: asyncio.Task | None = None

    def _start(self) -> None:
        if self._started:
            return
        self._started = True
        self._remote = _remote_mounts()
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            libc.inotify_init1.argtypes = [ctypes.c_int]
            libc.inotify_init1.restype = ctypes.c_int
            libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
            libc.inotify_add_watch.restype = ctypes.c_int
            libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
            libc.inotify_rm_watch.restype = ctypes.c_int
            descriptor = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
            if descriptor < 0:
                return
            self._libc = libc
            self._fd = descriptor
            asyncio.get_running_loop().add_reader(descriptor, self._read_events)
        except (AttributeError, OSError, NotImplementedError):
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None

    def subscribe(self, owner: str, bindings: tuple[FolderBinding, ...]) -> FolderSubscription:
        owner_limit = 32 if owner.startswith('share:') else 12
        if len(self.subscriptions) >= MAX_SUBSCRIPTIONS or sum(item.owner == owner for item in self.subscriptions) >= owner_limit:
            raise RuntimeError('Too many live folder connections')
        self._start()
        subscription = FolderSubscription(owner)
        self.subscriptions.add(subscription)
        try:
            self.update(subscription, bindings)
        except Exception:
            self.unsubscribe(subscription)
            raise
        return subscription

    def update(self, subscription: FolderSubscription, bindings: tuple[FolderBinding, ...]) -> bool:
        if subscription not in self.subscriptions:
            raise RuntimeError('Live folder connection is closed')
        for path in {binding.directory for binding in bindings}:
            directory = self.directories.get(path)
            if directory is not None and directory.descriptor is None:
                self._watch_native(directory)
        if bindings == subscription.bindings:
            return False
        new_paths = {binding.directory for binding in bindings}
        old_paths = {binding.directory for binding in subscription.bindings}
        if len(set(self.directories) | new_paths) > MAX_DIRECTORIES:
            raise RuntimeError('Too many live folders')
        try:
            for path in new_paths - set(self.directories):
                directory = _Directory(path)
                self._watch_native(directory)
                if directory.descriptor is None and sum(item.descriptor is None for item in self.directories.values()) >= MAX_FALLBACK_DIRECTORIES:
                    raise RuntimeError('Too many network folders are open')
                self.directories[path] = directory
            for path in new_paths:
                self.directories[path].listeners[subscription] = tuple(binding for binding in bindings if binding.directory == path)
            subscription.bindings = bindings
            for path in old_paths - new_paths:
                self.directories[path].listeners.pop(subscription, None)
        finally:
            self._remove_unused()
        if self._poll_task is None and any(item.descriptor is None for item in self.directories.values()):
            self._poll_task = asyncio.create_task(self._poll_fallback())
        return True

    def _watch_native(self, directory: _Directory) -> None:
        if self._fd is None or any(directory.path.is_relative_to(root) for root in self._remote):
            return
        # IN_ONLYDIR | IN_DONT_FOLLOW: never replace an authorized directory
        # watch with a symlink or a file during the bind race.
        descriptor = self._libc.inotify_add_watch(self._fd, os.fsencode(directory.path), _WATCH_MASK | 0x03000000)
        if descriptor >= 0:
            directory.descriptor = descriptor
            self._descriptors.setdefault(descriptor, set()).add(directory.path)

    async def ready(self, subscription: FolderSubscription) -> None:
        # Seed fallback snapshots before the initial browser refresh, so a file
        # arriving between that refresh and the first scan cannot be missed.
        for path in {binding.directory for binding in subscription.bindings}:
            directory = self.directories[path]
            if directory.descriptor is None:
                await directory.initialized.wait()

    def unsubscribe(self, subscription: FolderSubscription) -> None:
        self.subscriptions.discard(subscription)
        if subscription.timer is not None:
            subscription.timer.cancel()
        for directory in self.directories.values():
            directory.listeners.pop(subscription, None)
        self._remove_unused()
        if not self.subscriptions:
            self.close()

    def _remove_unused(self) -> None:
        for path, directory in list(self.directories.items()):
            if directory.listeners:
                continue
            del self.directories[path]
            descriptor = directory.descriptor
            if descriptor is not None:
                paths = self._descriptors[descriptor]
                paths.discard(path)
                if not paths:
                    del self._descriptors[descriptor]
                    self._libc.inotify_rm_watch(self._fd, descriptor)

    def _read_events(self) -> None:
        if self._fd is None:
            return
        try:
            payload = os.read(self._fd, 64 * 1024)
        except BlockingIOError:
            return
        offset = 0
        while offset + _EVENT.size <= len(payload):
            descriptor, mask, _cookie, size = _EVENT.unpack_from(payload, offset)
            offset += _EVENT.size
            name = os.fsdecode(payload[offset:offset + size].split(b'\0', 1)[0]) or None
            offset += size
            if mask & _OVERFLOW:
                for directory in self.directories.values():
                    directory.notify()
                continue
            if mask & _CREATE and not mask & _ISDIR:
                continue
            for path in tuple(self._descriptors.get(descriptor, ())):
                directory = self.directories.get(path)
                if directory is None:
                    continue
                directory.notify(name)
                if mask & (_DELETE_SELF | _MOVE_SELF | _UNMOUNT | _IGNORED):
                    # The old inode must never continue serving a replaced path.
                    directory.descriptor = None
                    self._descriptors[descriptor].discard(path)
            if descriptor in self._descriptors and not self._descriptors[descriptor]:
                del self._descriptors[descriptor]
                if not mask & _IGNORED:
                    self._libc.inotify_rm_watch(self._fd, descriptor)
        if self._poll_task is None and any(item.descriptor is None for item in self.directories.values()):
            self._poll_task = asyncio.create_task(self._poll_fallback())

    async def _poll_fallback(self) -> None:
        try:
            while True:
                directories = [item for item in self.directories.values() if item.descriptor is None]
                if not directories:
                    return
                for directory in directories:
                    bindings = tuple(binding for group in directory.listeners.values() for binding in group)
                    now = asyncio.get_running_loop().time()
                    reconcile = (
                        directory.published is None
                        or bindings != directory.snapshot_bindings
                        or now - directory.last_full_scan >= RECONCILE_SECONDS
                    )
                    pending = frozenset(directory.pending) | frozenset(
                        name for binding in bindings for name in (binding.names or ())
                    )
                    signature, current, complete = await asyncio.to_thread(
                        _fallback_snapshot, directory.path, bindings, directory.signature, pending, reconcile,
                    )
                    if self.directories.get(directory.path) is not directory:
                        continue
                    directory.signature = signature
                    if complete:
                        directory.snapshot_bindings = bindings
                        directory.last_full_scan = now
                    if directory.published is None:
                        if current is not None and directory.previous is None:
                            if directory.initialized.is_set():
                                directory.notify()
                            directory.previous = current
                            directory.published = current.copy()
                        directory.initialized.set()
                        continue
                    if current is None:
                        directory.notify()
                        directory.previous = directory.published = None
                        directory.pending.clear()
                        continue
                    previous = directory.previous
                    published = directory.published
                    checked_names = previous.keys() if complete else pending
                    for name in checked_names - current.keys():
                        if name in published:
                            directory.notify(name)
                        previous.pop(name, None)
                        published.pop(name, None)
                        directory.pending.discard(name)
                    for name, value in current.items():
                        if stat.S_ISDIR(value[0]) or previous.get(name) == value:
                            if published.get(name) != value:
                                directory.notify(name)
                            published[name] = value
                            directory.pending.discard(name)
                        else:
                            directory.pending.add(name)
                        previous[name] = value
                await asyncio.sleep(POLL_SECONDS)
        finally:
            if self._poll_task is asyncio.current_task():
                self._poll_task = None

    def close(self) -> None:
        for subscription in self.subscriptions:
            if subscription.timer is not None:
                subscription.timer.cancel()
            subscription.changed.set()
        self.subscriptions.clear()
        self.directories.clear()
        self._descriptors.clear()
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None
        if self._fd is not None:
            asyncio.get_running_loop().remove_reader(self._fd)
            os.close(self._fd)
            self._fd = None
        self._started = False


folder_events = FolderEventHub()
