"""Vue Sandboxes: create, read, save, restore and compare pages; show them safely."""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth import get_request_user
from app.services.horizons_fresh import require_horizon_project_access, touch_horizon_project
from app.services.sandboxes import (
    MAX_CONTENT_BYTES,
    MAX_EDITS,
    SANDBOX_DESCRIPTION_MAX_LENGTH,
    SANDBOX_NAME_MAX_LENGTH,
    VERSION_MESSAGE_MAX_LENGTH,
    apply_edits,
    check_content,
    content_length,
    create_sandbox,
    delete_sandbox,
    diff_versions,
    get_sandbox,
    get_version,
    list_sandboxes,
    list_versions,
    save_version,
    serialize_sandbox,
    serialize_version,
    update_sandbox,
)
from app.services.share_access import validate_share
from app.services.user_access import is_restricted_project_member

router = APIRouter(tags=['sandboxes'])

PAGE_GUIDE = (
    'A sandbox page is one complete HTML document. Put CSS in <style> and JavaScript in <script>; '
    'the page may also load scripts, styles, fonts and images from other websites. '
    'Vue.io shows the page in an isolated frame: it cannot read Vue.io data or call the Vue.io API, '
    'and it has no lasting storage, so put every value the page shows into the page itself.'
)


class SandboxCreate(BaseModel):
    name: str = Field(max_length=SANDBOX_NAME_MAX_LENGTH, description='Such as Budget or Delivery schedule.')
    description: str | None = Field(None, max_length=SANDBOX_DESCRIPTION_MAX_LENGTH, description='A short line that tells the team what the page is for.')
    content: str | None = Field(None, description='The first version of the page: one complete HTML document. Leave out to start blank.')
    message: str | None = Field(None, max_length=VERSION_MESSAGE_MAX_LENGTH, description='What the first version is, such as First draft of the budget.')


class SandboxUpdate(BaseModel):
    name: str | None = Field(None, max_length=SANDBOX_NAME_MAX_LENGTH)
    description: str | None = Field(None, max_length=SANDBOX_DESCRIPTION_MAX_LENGTH, description='Empty removes the description.')


class SandboxEdit(BaseModel):
    old_text: str = Field(description='Text that is in the newest version exactly once. Copy it exactly, with enough text around it to match once.')
    new_text: str = Field(description='The text that replaces old_text. Empty removes old_text.')


class SandboxSave(BaseModel):
    content: str | None = Field(None, description='The complete new page: one HTML document. For small changes, use edits instead.')
    edits: list[SandboxEdit] | None = Field(None, max_length=MAX_EDITS, description='Changes to the newest version, applied in order. Give content or edits, not both.')
    message: str | None = Field(None, max_length=VERSION_MESSAGE_MAX_LENGTH, description='What changed, such as Marked invoice 3 as paid. People see it in the history.')
    base_version: int | None = Field(None, ge=0, description='The version number your change starts from. If the sandbox has a newer version, Vue.io refuses the save so that you do not overwrite it.')


def _project_user(db: Session, project_id: str, vueio_session: str | None, x_vueio_agent_key: str | None, *, manage: bool = False) -> dict:
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    require_horizon_project_access(db, project_id, user, auth_mode=auth_mode, required_role='editor' if manage else 'viewer')
    # Restricted members see only their assigned work. A sandbox can hold
    # anything, such as a budget, so it stays with the people who manage the project.
    if is_restricted_project_member(user):
        raise HTTPException(status_code=403, detail='Only people who manage project content can open Vue Sandboxes.')
    return user


def _with_content(db: Session, payload: dict, version, *, offset: int, limit: int) -> dict:
    # A read of only the details, such as a check for a new version, does not
    # load the page itself.
    if limit == 0:
        total = content_length(db, version)
        chunk = ''
    else:
        text = version.content if version is not None else ''
        total = len(text)
        chunk = text[offset:offset + limit]
    end = offset + len(chunk)
    payload.update({
        'content': chunk,
        'offset': offset,
        'next_offset': end if end < total else None,
        'total_chars': total,
    })
    return payload


@router.get('/api/projects/{project_id}/sandboxes', summary='List Vue Sandboxes', openapi_extra={'x-mcp-tool': 'sandboxes_list'})
def list_project_sandboxes(project_id: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """List the Vue Sandboxes of a project, oldest first.

    A Vue Sandbox is a web page that the team builds for a project, such as a
    budget, a schedule or a client overview. `latest_version` is 0 for a blank
    sandbox. Read a page with sandbox_get.
    """
    _project_user(db, project_id, vueio_session, x_vueio_agent_key)
    return {'sandboxes': [serialize_sandbox(sandbox) for sandbox in list_sandboxes(db, project_id)]}


@router.post(
    '/api/projects/{project_id}/sandboxes',
    summary='Create a Vue Sandbox',
    description=(
        'Create a Vue Sandbox in a project. Give `content` to save the first version at once. '
        f'{PAGE_GUIDE} Returns the sandbox with its `id`; the team can open it in the project right away.'
    ),
    openapi_extra={'x-mcp-tool': 'sandbox_create'},
)
def create_project_sandbox(project_id: str, data: SandboxCreate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user = _project_user(db, project_id, vueio_session, x_vueio_agent_key, manage=True)
    if data.content is not None:
        check_content(data.content)
    sandbox = create_sandbox(db, project_id, name=data.name, description=data.description, user=user)
    version = None
    if data.content is not None:
        version, _changed = save_version(db, sandbox, data.content, user=user, message=data.message)
    touch_horizon_project(db, project_id)
    return serialize_sandbox(sandbox, version)


@router.get('/api/projects/{project_id}/sandboxes/{sandbox_ref}', summary='Read a Vue Sandbox', openapi_extra={'x-mcp-tool': 'sandbox_get'})
def get_project_sandbox(
    project_id: str,
    sandbox_ref: str,
    version: int | None = Query(None, ge=1, description='Read this version. Leave out for the newest.'),
    offset: int = Query(0, ge=0, description='The first character of the page to return.'),
    limit: int = Query(30000, ge=0, le=MAX_CONTENT_BYTES, description='The most characters of the page to return.'),
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Read a Vue Sandbox and its page.

    `sandbox_ref` is the sandbox id or slug. `content` is part of the page's
    HTML, from `offset`. When `next_offset` is not null, read again with
    offset set to it to get the rest. `version` describes the version read;
    `latest_version` is the newest. Use limit 0 to read only the details.
    """
    _project_user(db, project_id, vueio_session, x_vueio_agent_key)
    sandbox = get_sandbox(db, project_id, sandbox_ref)
    record = get_version(db, sandbox, version)
    return _with_content(db, serialize_sandbox(sandbox, record), record, offset=offset, limit=limit)


@router.put('/api/projects/{project_id}/sandboxes/{sandbox_ref}', summary='Rename a Vue Sandbox')
def update_project_sandbox(project_id: str, sandbox_ref: str, data: SandboxUpdate, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Change the name or description of a Vue Sandbox. Send only the fields to change.

    A new name also changes the slug. To change the page, use sandbox_save.
    """
    _project_user(db, project_id, vueio_session, x_vueio_agent_key, manage=True)
    sandbox = get_sandbox(db, project_id, sandbox_ref)
    sandbox = update_sandbox(db, sandbox, name=data.name, description=data.description, fields=set(data.model_fields_set))
    touch_horizon_project(db, project_id)
    return serialize_sandbox(sandbox, get_version(db, sandbox))


@router.delete('/api/projects/{project_id}/sandboxes/{sandbox_ref}', summary='Delete a Vue Sandbox')
def delete_project_sandbox(project_id: str, sandbox_ref: str, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Delete a Vue Sandbox permanently, with all its versions and share links."""
    _project_user(db, project_id, vueio_session, x_vueio_agent_key, manage=True)
    delete_sandbox(db, get_sandbox(db, project_id, sandbox_ref))
    touch_horizon_project(db, project_id)
    return {'status': 'deleted'}


@router.post(
    '/api/projects/{project_id}/sandboxes/{sandbox_ref}/versions',
    summary='Save a Vue Sandbox page',
    description=(
        'Save a new version of a Vue Sandbox page. Give the complete page in `content`, or small changes in `edits`. '
        'Each save adds a version; earlier versions stay in the history and people can restore them. '
        f'A page that is the same as the newest version adds nothing and returns `changed` false. {PAGE_GUIDE}'
    ),
    openapi_extra={'x-mcp-tool': 'sandbox_save'},
)
def save_project_sandbox(project_id: str, sandbox_ref: str, data: SandboxSave, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    user = _project_user(db, project_id, vueio_session, x_vueio_agent_key, manage=True)
    if (data.content is None) == (data.edits is None):
        raise HTTPException(status_code=422, detail='Give content or edits, not both.')
    sandbox = get_sandbox(db, project_id, sandbox_ref, for_update=True)
    if data.base_version is not None and data.base_version != sandbox.latest_version:
        raise HTTPException(status_code=409, detail=f'The sandbox has a newer version, {sandbox.latest_version}. Read it again, then save your change. Nothing was saved.')
    content = data.content
    if data.edits is not None:
        latest = get_version(db, sandbox)
        content = apply_edits(latest.content if latest is not None else '', [(edit.old_text, edit.new_text) for edit in data.edits])
    version, changed = save_version(db, sandbox, content, user=user, message=data.message)
    if changed:
        touch_horizon_project(db, project_id)
    return {**serialize_sandbox(sandbox, version), 'changed': changed}


@router.get('/api/projects/{project_id}/sandboxes/{sandbox_ref}/versions', summary='List the versions of a Vue Sandbox')
def list_project_sandbox_versions(
    project_id: str,
    sandbox_ref: str,
    limit: int = Query(50, ge=1, le=500),
    before: int | None = Query(None, ge=1, description='Return versions older than this number. Use next_before from the last result.'),
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """List the saved versions of a Vue Sandbox, newest first.

    Each version has its number, message, author, the agent that saved it if
    any, and the version it restores if it is a restore.
    """
    _project_user(db, project_id, vueio_session, x_vueio_agent_key)
    sandbox = get_sandbox(db, project_id, sandbox_ref)
    versions = list_versions(db, sandbox, limit=limit, before=before)
    more = len(versions) == limit and versions[-1].number > 1
    return {
        'latest_version': sandbox.latest_version,
        'versions': [serialize_version(version) for version in versions],
        'next_before': versions[-1].number if more else None,
    }


@router.post('/api/projects/{project_id}/sandboxes/{sandbox_ref}/versions/{number}/restore', summary='Restore a version of a Vue Sandbox')
def restore_project_sandbox_version(project_id: str, sandbox_ref: str, number: int, vueio_session: str = Cookie(None), x_vueio_agent_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Make an earlier version the page again.

    Vue.io saves a copy of that version as the newest version, so the history
    keeps every version.
    """
    user = _project_user(db, project_id, vueio_session, x_vueio_agent_key, manage=True)
    sandbox = get_sandbox(db, project_id, sandbox_ref, for_update=True)
    source = get_version(db, sandbox, number)
    if source is None:
        raise HTTPException(status_code=404, detail=f'Version {number} not found')
    version, changed = save_version(db, sandbox, source.content, user=user, restored_from=source.number)
    if changed:
        touch_horizon_project(db, project_id)
    return {**serialize_sandbox(sandbox, version), 'changed': changed}


@router.get('/api/projects/{project_id}/sandboxes/{sandbox_ref}/diff', summary='Compare two versions of a Vue Sandbox')
def diff_project_sandbox_versions(
    project_id: str,
    sandbox_ref: str,
    from_version: int = Query(ge=0, description='The older version. 0 is the blank page.'),
    to_version: int | None = Query(None, ge=1, description='The newer version. Leave out for the newest.'),
    limit: int = Query(2000, ge=10, le=5000, description='The most diff lines to return.'),
    vueio_session: str = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Show the lines that changed between two versions of a Vue Sandbox page.

    Each hunk has lines with `kind` ' ' (same), '-' (removed) or '+' (added)
    and their line numbers in the old and the new version.
    """
    _project_user(db, project_id, vueio_session, x_vueio_agent_key)
    sandbox = get_sandbox(db, project_id, sandbox_ref)
    old = get_version(db, sandbox, from_version) if from_version else None
    new = get_version(db, sandbox, to_version)
    result = diff_versions(old.content if old else '', new.content if new else '', limit=limit)
    return {'from_version': from_version, 'to_version': new.number if new else 0, **result}


@router.get('/api/projects/shared/{share_id}/sandbox')
def get_shared_sandbox(share_id: str, share_token: str | None = None, limit: int = Query(MAX_CONTENT_BYTES, ge=0, le=MAX_CONTENT_BYTES), db: Session = Depends(get_db)):
    """The page of a shared Vue Sandbox, for people who open its share link."""
    share = validate_share(share_id, None, db, ['sandbox'], share_token=share_token, track_access=False)
    sandbox = get_sandbox(db, share.project_id or '', share.sandbox_id or '')
    version = get_version(db, sandbox)
    payload = {
        'id': sandbox.id,
        'name': sandbox.name,
        'description': sandbox.description or '',
        'type': 'sandbox',
        'latest_version': sandbox.latest_version,
        'updated_at': version.created_at if version is not None else sandbox.created_at,
    }
    return _with_content(db, payload, version, offset=0, limit=limit)


# The frame that shows a sandbox page. Its policy puts the frame in a sandbox
# with its own empty origin: the page can run scripts, but it cannot read
# Vue.io cookies, storage or pages, and Vue.io never sends it a credential.
# Only Vue.io, in the window that holds the frame, can give it a page.
SANDBOX_FLAGS = 'allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads'
SANDBOX_FRAME_HEADERS = {
    'Content-Security-Policy': f"sandbox {SANDBOX_FLAGS}; frame-ancestors 'self'",
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-cache',
}
SANDBOX_FRAME_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Vue Sandbox</title>
<style>
html, body { margin: 0; height: 100%; background: #fff; }
iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block; }
</style>
</head>
<body>
<script>
(function () {
  'use strict';
  var appOrigin = new URL(location.href).origin;
  if (window.parent === window) return;
  var FLAGS = '__FLAGS__';

  // Runs first in every page. A sandboxed page has no storage or cookies of
  // its own, so keep them in memory and pages that use them still work.
  function prelude(scrollY) {
    function memoryStorage() {
      var items = new Map();
      return {
        get length() { return items.size; },
        key: function (index) { var keys = Array.from(items.keys()); return index < keys.length ? keys[index] : null; },
        getItem: function (key) { key = String(key); return items.has(key) ? items.get(key) : null; },
        setItem: function (key, value) { items.set(String(key), String(value)); },
        removeItem: function (key) { items.delete(String(key)); },
        clear: function () { items.clear(); }
      };
    }
    ['localStorage', 'sessionStorage'].forEach(function (name) {
      try { void window[name]; } catch (error) {
        try { Object.defineProperty(window, name, { value: memoryStorage(), configurable: true }); } catch (ignored) {}
      }
    });
    try { void document.cookie; } catch (error) {
      try { Object.defineProperty(document, 'cookie', { get: function () { return ''; }, set: function () {}, configurable: true }); } catch (ignored) {}
    }
    // Links to other pages open in a new tab. Links inside the page stay.
    document.addEventListener('click', function (event) {
      if (event.defaultPrevented || event.button !== 0) return;
      var link = event.target && event.target.closest ? event.target.closest('a[href]') : null;
      if (!link || link.hasAttribute('download')) return;
      var href = link.getAttribute('href') || '';
      if (href.charAt(0) === '#' || /^\\s*javascript:/i.test(href)) return;
      event.preventDefault();
      window.open(link.href, '_blank', 'noopener');
    });
    if (scrollY > 0) {
      var restore = function () { window.scrollTo(0, scrollY); };
      document.addEventListener('DOMContentLoaded', restore);
      window.addEventListener('load', restore);
    }
    var scrollTimer = 0;
    window.addEventListener('scroll', function () {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(function () {
        window.parent.postMessage({ type: 'vueio-sandbox-scroll', y: window.scrollY }, '*');
      }, 120);
    }, { passive: true });
  }

  function withPrelude(html, scrollY) {
    var script = '<script>(' + prelude + ')(' + (scrollY | 0) + ')<\\/script>';
    var match = /<head(?:\\s[^>]*)?>/i.exec(html) || /<html(?:\\s[^>]*)?>/i.exec(html) || /<!doctype[^>]*>/i.exec(html);
    if (!match) return script + html;
    var end = match.index + match[0].length;
    return html.slice(0, end) + script + html.slice(end);
  }

  var shown = null;
  var latest = null;
  var scrollY = 0;

  // A new page loads hidden behind the one on screen and replaces it when it
  // is ready, so live previews do not flash.
  function render(html, keepScroll, title) {
    if (!keepScroll) scrollY = 0;
    var frame = document.createElement('iframe');
    frame.setAttribute('sandbox', FLAGS);
    frame.setAttribute('allow', 'clipboard-write; fullscreen');
    frame.setAttribute('title', title || 'Sandbox page');
    if (shown) frame.style.visibility = 'hidden';
    latest = frame;
    var revealed = false;
    function reveal() {
      if (frame !== latest) { frame.remove(); return; }
      if (revealed) return;
      revealed = true;
      frame.style.visibility = '';
      if (shown && shown !== frame) shown.remove();
      shown = frame;
      window.parent.postMessage({ type: 'vueio-sandbox-shown' }, appOrigin);
    }
    frame.addEventListener('load', reveal);
    setTimeout(reveal, 1500);
    frame.srcdoc = withPrelude(html, scrollY);
    document.body.appendChild(frame);
  }

  window.addEventListener('message', function (event) {
    var data = event.data || {};
    if (event.source === window.parent && event.origin === appOrigin) {
      if (data.type === 'vueio-sandbox-render' && typeof data.html === 'string') render(data.html, Boolean(data.keepScroll), data.title);
    } else if (shown && event.source === shown.contentWindow && data.type === 'vueio-sandbox-scroll') {
      scrollY = Number(data.y) || 0;
    }
  });
  window.parent.postMessage({ type: 'vueio-sandbox-ready' }, appOrigin);
})();
</script>
</body>
</html>
""".replace('__FLAGS__', SANDBOX_FLAGS)


@router.get('/api/sandbox-frame', include_in_schema=False)
def sandbox_frame():
    return HTMLResponse(SANDBOX_FRAME_HTML, headers=SANDBOX_FRAME_HEADERS)
