from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings


def _existing_capacity_probe(path: Path) -> Path:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe


def ensure_path_capacity(
    path: Path,
    *,
    minimum_free_bytes: int,
    required_bytes: int = 0,
    unavailable_detail: str,
    insufficient_detail: str,
) -> None:
    """Require a free-space reserve on the filesystem containing ``path``."""
    minimum_free = max(0, int(minimum_free_bytes or 0))
    if not minimum_free:
        return
    try:
        free_bytes = shutil.disk_usage(_existing_capacity_probe(path)).free
    except OSError as exc:
        raise HTTPException(status_code=507, detail=unavailable_detail) from exc
    if free_bytes - max(0, int(required_bytes or 0)) < minimum_free:
        raise HTTPException(status_code=507, detail=insufficient_detail)


def ensure_data_capacity(required_bytes: int = 0) -> None:
    """Keep derived artifacts from consuming the app data volume's reserve."""
    settings = get_settings()
    ensure_path_capacity(
        settings.DATA_DIR,
        minimum_free_bytes=settings.DATA_MIN_FREE_BYTES,
        required_bytes=required_bytes,
        unavailable_detail='Unable to verify Vueio storage capacity',
        insufficient_detail='Vueio storage does not have enough free space',
    )
