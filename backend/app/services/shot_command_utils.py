from __future__ import annotations

from fastapi import HTTPException

from app.models import HorizonShotVersion
from app.services.horizons.common import SHOT_STATUS_ORDER


def normalize_shot_status(status: str | None) -> str:
    normalized = (status or '').strip().lower()
    if normalized not in SHOT_STATUS_ORDER:
        raise HTTPException(status_code=400, detail='Invalid shot status')
    return normalized


def next_version_label(existing_versions: list[HorizonShotVersion]) -> str:
    max_version = 0
    for version in existing_versions or []:
        try:
            max_version = max(max_version, int(str(version.label).strip()))
        except Exception:
            continue
    return str(max_version + 1)


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
