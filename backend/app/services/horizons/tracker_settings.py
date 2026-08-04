from __future__ import annotations

import json

from app.models import HorizonTracker
from app.services.external_urls import normalize_external_http_url
from app.services.project_delivery import normalize_delivery_logo_upload_name

from .common import DEFAULT_DELIVERY_MESSAGE, DEFAULT_TRACKER_SETTINGS, TRACKER_TOOL_ACCESSES

def _normalize_delivery_links(value) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    links = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = str(item.get('label') or '').strip()[:48]
        url = normalize_external_http_url(item.get('url'))
        if not label or not url:
            continue
        links.append({'label': label, 'url': url})
        if len(links) >= 4:
            break
    return links


def normalize_tracker_settings(value: dict | None) -> dict:
    tools = json.loads(json.dumps(DEFAULT_TRACKER_SETTINGS))
    if not isinstance(value, dict):
        return tools

    for key in ('comparison', 'details'):
        item = value.get(key)
        if not isinstance(item, dict):
            continue
        if 'enabled' in item:
            tools[key]['enabled'] = bool(item.get('enabled'))
        if 'access' in item:
            access = str(item.get('access') or '').strip().lower()
            if access in TRACKER_TOOL_ACCESSES:
                tools[key]['access'] = access
        elif key == 'comparison' and 'share_access' in item:
            tools[key]['access'] = 'all' if item.get('share_access') is True else 'team'

    brief_preview = value.get('brief_preview')
    if isinstance(brief_preview, dict) and 'enabled' in brief_preview:
        tools['brief_preview']['enabled'] = bool(brief_preview.get('enabled'))

    version_review = value.get('version_review')
    if isinstance(version_review, dict) and 'enabled' in version_review:
        tools['version_review']['enabled'] = bool(version_review.get('enabled'))

    delivery = value.get('delivery')
    if isinstance(delivery, dict):
        if 'enabled' in delivery:
            tools['delivery']['enabled'] = bool(delivery.get('enabled'))
        if 'message' in delivery:
            message = str(delivery.get('message') or '').strip()
            tools['delivery']['message'] = message or DEFAULT_DELIVERY_MESSAGE
        if 'notes' in delivery:
            tools['delivery']['notes'] = str(delivery.get('notes') or '').strip()[:1200]
        if 'links' in delivery:
            tools['delivery']['links'] = _normalize_delivery_links(delivery.get('links'))
        if 'logo_upload_name' in delivery:
            tools['delivery']['logo_upload_name'] = normalize_delivery_logo_upload_name(delivery.get('logo_upload_name'))
    return tools


def tracker_settings_for(tracker: HorizonTracker) -> dict:
    try:
        raw_tools = json.loads(tracker.settings_json or '{}')
    except Exception:
        raw_tools = {}
    return normalize_tracker_settings(raw_tools)


def tracker_tool_enabled_for_context(
    tracker: HorizonTracker,
    tool_key: str,
    *,
    user: dict | None = None,
    access_role: str | None = None,
    share: bool = False,
) -> bool:
    tool = tracker_settings_for(tracker).get(tool_key) or {}
    if not tool.get('enabled'):
        return False
    if tool_key == 'delivery':
        return True

    access = str(tool.get('access') or 'team').strip().lower()
    if access == 'all':
        return True
    if share:
        return False
    if access == 'admin':
        return bool(user and user.get('role') == 'admin')
    return bool(access_role)
