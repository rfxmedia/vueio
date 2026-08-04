from __future__ import annotations

import re


def slugify(value: str | None, fallback: str) -> str:
    normalized = str(value or '').strip().lower()
    normalized = re.sub(r'[^a-z0-9]+', '-', normalized).strip('-')
    return normalized or fallback


def safe_name_part(value: str | None, fallback: str) -> str:
    normalized = re.sub(r'[^A-Za-z0-9._-]+', '-', str(value or '').strip()).strip('-._')
    return normalized or fallback
