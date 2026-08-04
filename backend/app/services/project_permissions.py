from __future__ import annotations

import stat
from pathlib import Path

from app.config import get_settings


def make_project_path_smb_mutable(path: Path) -> None:
    """Apply the configured mode to app-created project content.

    The defaults keep owner/group write access without making content
    world-writable. Existing installations that rely on permissive SMB modes
    can explicitly set PROJECT_DIRECTORY_MODE=0777 and PROJECT_FILE_MODE=0666.
    """
    if path.is_symlink():
        return
    mode = path.stat().st_mode
    current_permissions = stat.S_IMODE(mode)
    settings = get_settings()
    if stat.S_ISDIR(mode):
        desired_permissions = settings.project_directory_mode
    else:
        desired_permissions = settings.project_file_mode
    desired_permissions |= current_permissions & 0o7000
    if current_permissions != desired_permissions:
        path.chmod(desired_permissions)


def make_project_tree_smb_mutable(path: Path) -> None:
    """Apply SMB-editable permissions to a copied project subtree."""
    make_project_path_smb_mutable(path)
    if not path.is_dir():
        return
    for child in path.rglob('*'):
        make_project_path_smb_mutable(child)
