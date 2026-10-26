from __future__ import annotations

import re

from fastapi import HTTPException

from app.models import HorizonShotVersion
from app.services.horizons.common import SHOT_STATUS_ORDER


def normalize_shot_status(status: str | None) -> str:
    normalized = (status or '').strip().lower()
    if normalized not in SHOT_STATUS_ORDER:
        raise HTTPException(status_code=400, detail='Invalid shot status')
    return normalized


_NUMBERED_LABEL = re.compile(r'^(v?)(\d+)$', re.IGNORECASE)


def next_version_label(existing_versions: list[HorizonShotVersion]) -> str:
    """Return the label after the highest numbered one, in its style: 3 after 2, v002 after v001."""
    highest: tuple[int, str, int] | None = None
    for version in existing_versions or []:
        match = _NUMBERED_LABEL.match(str(version.label or '').strip())
        if match and (highest is None or int(match.group(2)) > highest[0]):
            highest = (int(match.group(2)), match.group(1), len(match.group(2)))
    if highest is None:
        return '1'
    number, prefix, width = highest
    return f'{prefix}{number + 1:0{width}d}'


def normalize_bulk_shot_refs(shot_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for shot_id in shot_ids or []:
        value = str(shot_id or '').strip()
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    if not normalized:
        raise HTTPException(status_code=400, detail='At least one shot is required')
    if len(normalized) > 250:
        raise HTTPException(status_code=400, detail='Bulk shot operations are limited to 250 shots')
    return normalized
