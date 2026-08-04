from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppTheme

DEFAULT_THEME_COLORS = {
    '--v-bg-base': '#0a0f14',
    '--v-surface-panel': '#141c23',
    '--v-surface-inline': '#1a242c',
    '--v-text': '#eef5f4',
    '--v-text-secondary': '#c9d6d8',
    '--v-accent': '#76dda8',
    '--v-danger': '#ff6b6b',
    '--v-warning': '#d9bd76',
    '--v-info': '#83b8d8',
}

ALLOWED_THEME_KEYS = set(DEFAULT_THEME_COLORS.keys())


def _normalize_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned.startswith('#'):
        return None
    payload = cleaned[1:]
    if len(payload) == 3 and all(char in '0123456789abcdef' for char in payload):
        return '#' + ''.join(char * 2 for char in payload)
    if len(payload) == 6 and all(char in '0123456789abcdef' for char in payload):
        return cleaned
    return None


def sanitize_theme_colors(colors: dict[str, Any] | None) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in (colors or {}).items():
        if key not in ALLOWED_THEME_KEYS:
            continue
        normalized = _normalize_hex(value)
        if normalized:
            sanitized[key] = normalized
    return sanitized


def resolve_theme_colors(colors: dict[str, Any] | None) -> dict[str, str]:
    return {
        **DEFAULT_THEME_COLORS,
        **sanitize_theme_colors(colors),
    }


def get_app_theme_record(db: Session) -> AppTheme | None:
    return db.query(AppTheme).order_by(AppTheme.id.asc()).first()


def serialize_app_theme(record: AppTheme | None) -> dict[str, Any]:
    raw_colors: dict[str, Any] = {}
    if record and record.colors_json:
        try:
            raw_colors = json.loads(record.colors_json)
        except Exception:
            raw_colors = {}
    return {
        'colors': resolve_theme_colors(raw_colors),
        'updated_at': record.updated_at if record else None,
        'updated_by': record.updated_by if record else None,
    }


def save_app_theme(db: Session, colors: dict[str, Any], updated_by: str | None = None) -> AppTheme:
    record = get_app_theme_record(db)
    now = time.time()
    sanitized = sanitize_theme_colors(colors)
    if not record:
        record = AppTheme(colors_json=json.dumps(sanitized), updated_by=updated_by, created_at=now, updated_at=now)
        db.add(record)
    else:
        record.colors_json = json.dumps(sanitized)
        record.updated_by = updated_by
        record.updated_at = now
    db.commit()
    db.refresh(record)
    return record


def reset_app_theme(db: Session, updated_by: str | None = None) -> AppTheme:
    return save_app_theme(db, {}, updated_by=updated_by)
