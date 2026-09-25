"""Bounded camera bookmarks in the existing annotation target column."""
from __future__ import annotations

import json
import math
from fastapi import HTTPException

MAX_ANNOTATION_TARGET_LENGTH = 2048


def validate_annotation_target(value: str | None) -> None:
    if not value:
        return
    if len(value) > MAX_ANNOTATION_TARGET_LENGTH:
        raise HTTPException(413, 'Comment annotation target is too large')
    try:
        target = json.loads(value)
        if not isinstance(target, dict):
            raise ValueError()
        # Preserve existing PDF targets. Only the new model payload is expanded.
        if target.get('kind') != 'model-view':
            if len(value) > 100:
                raise ValueError()
            return
        def number(value, low, high):
            return type(value) in (float, int) and math.isfinite(value) and low <= value <= high
        def vector(value):
            return isinstance(value, list) and len(value) == 3 and all(number(n, -1e9, 1e9) for n in value)
        if target.get('version') != 1 or not all(vector(target.get(key)) for key in ('position', 'target', 'up')):
            raise ValueError()
        if sum(n * n for n in target['up']) < 1e-12 or sum((a-b)**2 for a,b in zip(target['position'], target['target'])) < 1e-12:
            raise ValueError()
        if not number(target.get('fov'), 10, 100) or not number(target.get('aspect'), .05, 20):
            raise ValueError()
        if type(target.get('clip')) is not int or not 0 <= target['clip'] <= 1000:
            raise ValueError()
        if target.get('time') is not None and not number(target['time'], 0, 86400):
            raise ValueError()
        light = target['lighting']
        if (light['preset'] not in ('studio', 'daylight', 'night')
                or not number(light['intensity'], 0, 3) or not number(light['rotation'], 0, 360)):
            raise ValueError()
    except (ValueError, TypeError, KeyError, OverflowError):
        raise HTTPException(422, 'Invalid annotation view') from None
