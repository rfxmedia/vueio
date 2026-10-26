from __future__ import annotations

import re
from pathlib import PurePosixPath


def slugify(value: str | None, fallback: str) -> str:
    normalized = str(value or '').strip().lower()
    normalized = re.sub(r'[^a-z0-9]+', '-', normalized).strip('-')
    return normalized or fallback


def safe_name_part(value: str | None, fallback: str) -> str:
    normalized = re.sub(r'[^A-Za-z0-9._-]+', '-', str(value or '').strip()).strip('-._')
    return normalized or fallback


# Characters that Windows, macOS or Linux refuse in file names.
_UNSAFE_FILE_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]+')
_WINDOWS_RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{n}' for n in range(1, 10)), *(f'LPT{n}' for n in range(1, 10))}


def readable_file_name_part(value: str | None, fallback: str, *, max_length: int = 120) -> str:
    """Keep a name as people wrote it (spaces, accents), without characters file systems refuse."""
    normalized = _UNSAFE_FILE_CHARACTERS.sub('-', str(value or ''))
    normalized = re.sub(r'\s+', ' ', normalized).strip(' .-')[:max_length].rstrip(' .-')
    return normalized or fallback


def version_tag(label: str | None) -> str:
    """The version as the tracker shows it: 8 becomes V8, v008 becomes V008."""
    raw = str(label or '').strip()
    if re.fullmatch(r'\d+', raw):
        return f'V{raw}'
    if raw[:1] in ('v', 'V') and raw[1:2].isdigit():
        return f'V{raw[1:]}'
    return raw


def tracker_version_file_name(shot_name: str | None, label: str | None, source_name: str) -> str:
    """Name a shot version for download: the shot's tracker name, the version, the file's extension."""
    extension = PurePosixPath(source_name or '').suffix
    shot_part = readable_file_name_part(shot_name, PurePosixPath(source_name or '').stem or 'shot')
    tag = readable_file_name_part(version_tag(label), '', max_length=40)
    if tag:
        return f'{shot_part}_{tag}{extension}'
    # Windows refuses names such as CON.mp4.
    return f'{shot_part}_{extension}' if shot_part.upper() in _WINDOWS_RESERVED_NAMES else f'{shot_part}{extension}'
