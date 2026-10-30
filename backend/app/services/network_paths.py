"""Full file paths as computers on the studio network see them.

An administrator enters the network path of a storage location once, such as
\\\\nas\\Media. Vue.io then gives the path of each file in that location in the
form Windows (\\\\nas\\Media\\...), macOS (/Volumes/Media/...) and other systems
(smb://nas/Media/...) understand. Vue.io cannot see whether a computer reaches
the share; the path only names the file.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import StorageNetworkPath
from app.services.file_access import check_folder_read_permission
from app.services.projects import configured_project_storage_catalog
from app.services.user_access import has_app_access, is_admin_user

NETWORK_PATH_MAX_LENGTH = 400
NETWORK_PATH_HINT = r'Enter a network path, such as \\nas\Media or smb://nas/Media.'
_SERVER = re.compile(r'[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?')
_UNSAFE_PART = re.compile(r'[\x00-\x1f\x7f<>:"|?*]')


def normalize_network_path(value: str) -> str:
    """Return the \\\\server\\share\\folder form, or raise ValueError."""
    text = str(value or '').strip()
    if text[:6].lower() == 'smb://':
        # Finder shows smb:// addresses URL-encoded, such as My%20Share.
        text = unquote(text[6:])
    elif text.startswith(('\\\\', '//')):
        text = text[2:]
    elif re.match(r'[A-Za-z]:', text):
        raise ValueError(
            'A drive letter works only on one computer. Enter the network path of the drive. '
            'On Windows, the net use command shows it, such as \\\\nas\\Media.'
        )
    elif text.startswith('/Volumes/'):
        raise ValueError(
            'Enter the server name too, such as smb://nas/Media. '
            'On a Mac, select the drive in Finder and choose Get Info to see it.'
        )
    else:
        raise ValueError(NETWORK_PATH_HINT)
    parts = [part for part in re.split(r'[\\/]+', text) if part]
    if len(parts) < 2:
        raise ValueError(NETWORK_PATH_HINT)
    server = parts[0].rsplit('@', 1)[-1]
    # Finder can name a server by its Bonjour service, such as nas._smb._tcp.local.
    if server.lower().endswith('._smb._tcp.local'):
        server = server[:-len('._smb._tcp.local')] + '.local'
    if not _SERVER.fullmatch(server) or any(part in {'.', '..'} or _UNSAFE_PART.search(part) for part in parts[1:]):
        raise ValueError(NETWORK_PATH_HINT)
    canonical = '\\\\' + '\\'.join([server, *parts[1:]])
    if len(canonical) > NETWORK_PATH_MAX_LENGTH:
        raise ValueError('The network path is too long.')
    return canonical


def network_path_forms(network_path: str, relative_parts: tuple[str, ...] = ()) -> dict:
    server, *parts = network_path[2:].split('\\')
    parts = [*parts, *relative_parts]
    return {
        'windows': '\\\\' + '\\'.join([server, *parts]),
        'mac': '/Volumes/' + '/'.join(parts),
        'smb': 'smb://' + '/'.join([server, *parts]),
    }


def network_paths_by_root(db: Session) -> dict[str, str]:
    return {row.root_id: row.network_path for row in db.query(StorageNetworkPath).all()}


def set_network_path(db: Session, root_id: str, value: str, username: str | None) -> str | None:
    """Save or clear the network path of a storage location. Raises ValueError."""
    row = db.get(StorageNetworkPath, root_id)
    if not str(value or '').strip():
        if row is not None:
            db.delete(row)
            db.commit()
        return None
    canonical = normalize_network_path(value)
    if row is None:
        row = StorageNetworkPath(root_id=root_id, network_path=canonical)
        db.add(row)
    row.network_path = canonical
    row.updated_by = username
    row.updated_at = time.time()
    db.commit()
    return canonical


def _can_see_paths(user: dict | None) -> bool:
    return bool(user) and (is_admin_user(user) or has_app_access(user, 'file_browser'))


def user_has_network_paths(db: Session, user: dict | None) -> bool:
    return _can_see_paths(user) and db.query(StorageNetworkPath.root_id).first() is not None


def file_network_path(db: Session, user: dict | None, full_path: Path | None) -> dict | None:
    """The network path of a file or folder for this person, or None.

    People see paths when they are administrators, or have File Browser access
    and may read that folder in the File Browser.
    """
    if full_path is None or not _can_see_paths(user):
        return None
    target = Path(full_path).resolve(strict=False)
    for root_id, item in configured_project_storage_catalog().items():
        if target.is_relative_to(item['path']):
            break
    else:
        return None
    row = db.get(StorageNetworkPath, root_id)
    if row is None:
        return None
    media_root = get_settings().MEDIA_ROOT.resolve(strict=False)
    if target.is_relative_to(media_root) and not check_folder_read_permission(user, '/'.join(target.relative_to(media_root).parts)):
        return None
    return network_path_forms(row.network_path, target.relative_to(item['path']).parts)
