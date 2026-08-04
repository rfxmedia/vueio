from __future__ import annotations

import html
import os
import re
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.error import URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import get_settings
from app.models import ShareLink
from app.services.external_urls import normalize_external_http_url, normalize_http_origin
from app.services.horizon_pages import get_horizon_page_by_ref
from app.services.horizons_fresh import (
    get_horizon_media_asset_by_path,
    get_horizon_project,
    get_horizon_tracker_by_ref,
    get_horizon_tracker_for_share,
)
from app.services.media import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from app.services.projects import load_project
from app.services.share_access import is_horizons_share_project

router = APIRouter(tags=['share-preview'])
settings = get_settings()

INDEX_CACHE_TTL_SECONDS = 30
INDEX_FETCH_TIMEOUT_SECONDS = 1.5
_index_cache: dict[str, object] = {'html': None, 'expires_at': 0.0}

FALLBACK_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vue</title>
</head>
<body>
  <div id="app"></div>
</body>
</html>
"""


@dataclass(frozen=True)
class SharePreview:
    title: str
    description: str
    image_path: str | None = None
    image_alt: str | None = None


def _load_spa_index_html() -> str:
    source_url = os.environ.get('VUEIO_UI_INDEX_URL', '').strip()
    if not source_url:
        return FALLBACK_INDEX_HTML
    parsed_source = urlsplit(source_url)
    if (
        parsed_source.scheme not in {'http', 'https'}
        or not parsed_source.hostname
        or parsed_source.username is not None
        or parsed_source.password is not None
    ):
        return FALLBACK_INDEX_HTML

    now = time.time()
    cached_html = _index_cache.get('html')
    cached_expires_at = float(_index_cache.get('expires_at') or 0)
    if cached_html and cached_expires_at > now:
        return str(cached_html)

    try:
        request = UrlRequest(source_url, headers={'User-Agent': 'vueio-share-preview/1.0'})
        # Scheme and authority are constrained above; this never opens local files.
        with urlopen(request, timeout=INDEX_FETCH_TIMEOUT_SECONDS) as response:  # nosec B310
            index_html = response.read().decode('utf-8')
    except (OSError, UnicodeDecodeError, URLError):
        return FALLBACK_INDEX_HTML

    if '</head' in index_html.lower():
        _index_cache['html'] = index_html
        _index_cache['expires_at'] = now + INDEX_CACHE_TTL_SECONDS
        return index_html
    return FALLBACK_INDEX_HTML


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _share_is_public(share: ShareLink | None) -> bool:
    if not share or not share.is_active:
        return False
    if share.expires_at and share.expires_at < time.time():
        return False
    return True


def _is_media_path(path: str | None) -> bool:
    suffix = PurePosixPath(path or '').suffix.lower()
    return suffix in IMAGE_EXTENSIONS or suffix in VIDEO_EXTENSIONS


def _filename(path: str | None, fallback: str = 'Vue Share') -> str:
    value = str(path or '').strip().strip('/')
    if not value:
        return fallback
    return PurePosixPath(value).name or fallback


def _request_origin(request: Request) -> str:
    configured = normalize_http_origin(settings.VUEIO_PUBLIC_BASE_URL)
    if configured:
        return configured
    proto = request.headers.get('x-forwarded-proto') or request.url.scheme
    host = request.headers.get('x-forwarded-host') or request.headers.get('host') or request.url.netloc
    forwarded = normalize_http_origin(f'{proto}://{host}')
    if forwarded:
        return forwarded
    return normalize_http_origin(f'{request.url.scheme}://{request.url.netloc}')


def _request_public_url(request: Request) -> str:
    origin = _request_origin(request)
    raw_path = request.scope.get('raw_path') or b''
    path = raw_path.decode('latin-1') if raw_path else request.url.path
    query = f'?{request.url.query}' if request.url.query else ''
    return f'{origin}{path}{query}' if origin else f'{path}{query}'


def _absolute_url(request: Request, path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith('http://') or path.startswith('https://'):
        return normalize_external_http_url(path) or None
    origin = _request_origin(request)
    if not origin:
        return None
    prefix = '' if path.startswith('/') else '/'
    return f'{origin}{prefix}{path}'


def _route_path(*parts: str) -> str:
    return '/' + '/'.join(quote(part.strip('/'), safe='') for part in parts if part is not None)


def _shared_thumbnail_path(share_id: str, path: str | None = None) -> str:
    params = {'cached_only': 'true'}
    if path:
        params['path'] = path.strip('/')
    return f'{_route_path("api", "projects", "shared", share_id, "thumbnail")}?{urlencode(params)}'


def _shared_media_asset_thumbnail_path(share_id: str, media_asset_id: str) -> str:
    return (
        f'{_route_path("api", "projects", "shared", share_id, "media-assets", media_asset_id, "thumbnail")}'
        '?cached_only=true'
    )


def _project_thumbnail_path(share: ShareLink) -> str | None:
    if not share.project_id:
        return None
    params = urlencode({'share_id': share.id, 'cached_only': 'true'})
    if is_horizons_share_project(share):
        return f'{_route_path("api", "horizons", "projects", share.project_id, "thumbnail", "resolved")}?{params}'
    return f'{_route_path("api", "project-thumbnail", share.project_id, "resolved")}?{params}'


def _project_title(db: Session, share: ShareLink) -> str:
    if not share.project_id:
        return 'Vue Share'
    if is_horizons_share_project(share):
        try:
            return get_horizon_project(db, share.project_id).title
        except Exception:
            return _filename(share.project_id)
    try:
        project = load_project(share.project_id)
        return str(project.get('title') or project.get('name') or _filename(share.project_id))
    except Exception:
        return _filename(share.project_id)


def _tracker_title(db: Session, share: ShareLink, project_title: str, route_tracker: str | None = None) -> str:
    tracker_ref = route_tracker or share.tracker_name
    if not tracker_ref:
        return project_title
    if is_horizons_share_project(share) and share.project_id:
        try:
            tracker = (
                get_horizon_tracker_for_share(db, share)
                if share.share_type == 'tracker'
                else get_horizon_tracker_by_ref(db, share.project_id, tracker_ref)
            )
            return f'{tracker.name} - {project_title}'
        except Exception:
            pass
    return f'{tracker_ref} - {project_title}'


def _page_title(db: Session, share: ShareLink, project_title: str) -> str:
    if is_horizons_share_project(share) and share.project_id and share.page_id:
        try:
            page = get_horizon_page_by_ref(db, share.project_id, share.page_id)
            return f'{page.title} - {project_title}'
        except Exception:
            pass
    return project_title


def _project_file_thumbnail_path(db: Session, share: ShareLink, route_path: str | None = None) -> str | None:
    path = (route_path or share.path or '').strip('/')
    if not _is_media_path(path):
        return None
    if is_horizons_share_project(share) and share.project_id:
        asset = get_horizon_media_asset_by_path(db, share.project_id, path)
        if asset:
            return _shared_media_asset_thumbnail_path(share.id, asset.id)
    return _shared_thumbnail_path(share.id, path if route_path else None)


def _build_share_preview(
    request: Request,
    db: Session,
    share_id: str,
    *,
    route_path: str | None = None,
    route_tracker: str | None = None,
) -> SharePreview:
    share = db.query(ShareLink).filter(ShareLink.id == share_id).first()
    if not _share_is_public(share):
        return SharePreview(title='Vue Share', description='Open this shared Vue link.')
    assert share is not None

    if share.password_hash:
        return SharePreview(
            title='Protected Vue Share',
            description='Open this link to view the protected share.',
        )

    project_title = _project_title(db, share)
    if share.request_files:
        return SharePreview(
            title=f'File request for {_filename(share.path, fallback=project_title)}',
            description='Upload requested files securely in Vue.',
        )

    description = 'Open this shared item in Vue.'
    share_type = share.share_type or 'file'

    if share_type == 'tracker':
        return SharePreview(
            title=_tracker_title(db, share, project_title, route_tracker=route_tracker),
            description='Open this shared tracker in Vue.',
            image_path=_project_thumbnail_path(share),
            image_alt=project_title,
        )

    if share_type == 'page':
        return SharePreview(
            title=_page_title(db, share, project_title),
            description='Open this shared page in Vue.',
            image_path=_project_thumbnail_path(share),
            image_alt=project_title,
        )

    if share_type == 'project':
        return SharePreview(
            title=project_title,
            description='Open this shared project in Vue.',
            image_path=_project_thumbnail_path(share),
            image_alt=project_title,
        )

    if share_type in {'project-file', 'file'}:
        media_path = (route_path or share.path or '').strip('/')
        return SharePreview(
            title=_filename(media_path, fallback=project_title),
            description=description,
            image_path=_project_file_thumbnail_path(db, share, route_path=route_path)
            if share_type == 'project-file'
            else (_shared_thumbnail_path(share.id, route_path) if _is_media_path(media_path) else None),
            image_alt=_filename(media_path, fallback=project_title),
        )

    if share_type in {'project-folder', 'folder'}:
        media_path = (route_path or '').strip('/')
        folder_title = _filename(share.path, fallback=project_title)
        if media_path and _is_media_path(media_path):
            image_path = (
                _project_file_thumbnail_path(db, share, route_path=media_path)
                if share_type == 'project-folder'
                else _shared_thumbnail_path(share.id, media_path)
            )
            return SharePreview(
                title=_filename(media_path, fallback=folder_title),
                description=description,
                image_path=image_path,
                image_alt=_filename(media_path, fallback=folder_title),
            )
        return SharePreview(
            title=folder_title,
            description='Open this shared folder in Vue.',
            image_path=_project_thumbnail_path(share) if share_type == 'project-folder' else None,
            image_alt=project_title if share_type == 'project-folder' else None,
        )

    return SharePreview(title=project_title, description=description, image_path=_project_thumbnail_path(share))


def _meta_tags(request: Request, preview: SharePreview) -> str:
    title = preview.title or 'Vue Share'
    description = preview.description or 'Open this shared Vue link.'
    image_url = _absolute_url(request, preview.image_path)
    current_url = _request_public_url(request)
    tags = [
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Vue">',
        f'<meta property="og:title" content="{_escape(title)}">',
        f'<meta property="og:description" content="{_escape(description)}">',
        f'<meta property="og:url" content="{_escape(current_url)}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if image_url else "summary"}">',
        f'<meta name="twitter:title" content="{_escape(title)}">',
        f'<meta name="twitter:description" content="{_escape(description)}">',
    ]
    if image_url:
        image_alt = preview.image_alt or title
        tags.extend([
            f'<meta property="og:image" content="{_escape(image_url)}">',
            f'<meta property="og:image:secure_url" content="{_escape(image_url)}">',
            f'<meta property="og:image:alt" content="{_escape(image_alt)}">',
            f'<meta name="twitter:image" content="{_escape(image_url)}">',
        ])
    return '\n  '.join(tags)


def _inject_preview_tags(index_html: str, request: Request, preview: SharePreview) -> str:
    tags = _meta_tags(request, preview)
    title_tag = f'<title>{_escape(preview.title or "Vue")}</title>'
    html_with_title = re.sub(r'<title>.*?</title>', title_tag, index_html, count=1, flags=re.IGNORECASE | re.DOTALL)
    if html_with_title == index_html and '<head' in index_html.lower():
        html_with_title = re.sub(r'(<head[^>]*>)', rf'\1\n  {title_tag}', index_html, count=1, flags=re.IGNORECASE)
    match = re.search(r'</head\s*>', html_with_title, flags=re.IGNORECASE)
    if match:
        return html_with_title[:match.start()] + f'\n  {tags}\n' + html_with_title[match.start():]
    return f'<!doctype html><html><head>{title_tag}\n  {tags}</head><body><div id="app"></div></body></html>'


def _render_share_preview(
    request: Request,
    db: Session,
    share_id: str,
    *,
    route_path: str | None = None,
    route_tracker: str | None = None,
) -> HTMLResponse:
    preview = _build_share_preview(
        request,
        db,
        share_id,
        route_path=route_path,
        route_tracker=route_tracker,
    )
    return HTMLResponse(_inject_preview_tags(_load_spa_index_html(), request, preview))


@router.get('/s/{share_id}', response_class=HTMLResponse)
def shared_nas_preview(request: Request, share_id: str, db: Session = Depends(get_db)):
    return _render_share_preview(request, db, share_id)


@router.get('/s/{share_id}/{route_path:path}', response_class=HTMLResponse)
def shared_nas_path_preview(request: Request, share_id: str, route_path: str, db: Session = Depends(get_db)):
    return _render_share_preview(request, db, share_id, route_path=route_path)


@router.get('/p/{share_id}', response_class=HTMLResponse)
def shared_project_preview(request: Request, share_id: str, db: Session = Depends(get_db)):
    return _render_share_preview(request, db, share_id)


@router.get('/p/{share_id}/t/{route_tracker:path}', response_class=HTMLResponse)
def shared_tracker_preview(request: Request, share_id: str, route_tracker: str, db: Session = Depends(get_db)):
    return _render_share_preview(request, db, share_id, route_tracker=route_tracker)


@router.get('/p/{share_id}/f', response_class=HTMLResponse)
def shared_project_file_preview(request: Request, share_id: str, db: Session = Depends(get_db)):
    return _render_share_preview(request, db, share_id)


@router.get('/p/{share_id}/f/{route_path:path}', response_class=HTMLResponse)
def shared_project_file_path_preview(
    request: Request,
    share_id: str,
    route_path: str,
    db: Session = Depends(get_db),
):
    return _render_share_preview(request, db, share_id, route_path=route_path)
