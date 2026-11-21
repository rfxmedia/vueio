"""Vue Sandboxes: web pages that a project builds, with a saved history.

A sandbox page is one HTML document. Browsers run it in an isolated frame
(see routes/sandboxes.py, /api/sandbox-frame), so the page cannot reach
Vue.io, its data, or the person who looks at it. Every save adds a version;
a version never changes.
"""
from __future__ import annotations

import difflib
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import HorizonSandbox, HorizonSandboxVersion, ShareLink
from app.services.auth import get_request_agent_identity
from app.services.naming import slugify

SANDBOX_NAME_MAX_LENGTH = 120
SANDBOX_DESCRIPTION_MAX_LENGTH = 240
VERSION_MESSAGE_MAX_LENGTH = 200
MAX_CONTENT_BYTES = 5 * 1024 * 1024
MAX_EDITS = 100
DIFF_CONTEXT_LINES = 3
# A diff line longer than this is cut. Minified pages can be one huge line.
DIFF_LINE_MAX_CHARS = 2000
# Line matching can take minutes on long, repetitive pages. A changed part
# longer than this shows as one replaced block instead.
DIFF_MATCH_MAX_LINES = 1000
SLUG_ATTEMPTS = 3


def list_sandboxes(db: Session, project_id: str) -> list[HorizonSandbox]:
    return (
        db.query(HorizonSandbox)
        .filter(HorizonSandbox.project_id == project_id)
        .order_by(HorizonSandbox.created_at.asc())
        .all()
    )


def get_sandbox(db: Session, project_id: str, sandbox_ref: str, *, for_update: bool = False) -> HorizonSandbox:
    ref = str(sandbox_ref or '').strip()
    query = (
        db.query(HorizonSandbox)
        .filter(HorizonSandbox.project_id == project_id)
        .filter((HorizonSandbox.id == ref) | (HorizonSandbox.slug == ref))
    )
    sandbox = (query.with_for_update() if for_update else query).first()
    if sandbox is None:
        raise HTTPException(status_code=404, detail='Sandbox not found')
    return sandbox


def get_version(db: Session, sandbox: HorizonSandbox, number: int | None = None) -> HorizonSandboxVersion | None:
    """The version with this number, or the newest one. None for a blank sandbox."""
    number = sandbox.latest_version if number is None else number
    if not number:
        return None
    version = (
        db.query(HorizonSandboxVersion)
        .filter(HorizonSandboxVersion.sandbox_id == sandbox.id)
        .filter(HorizonSandboxVersion.number == number)
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail=f'Version {number} not found')
    return version


def content_length(db: Session, version: HorizonSandboxVersion | None) -> int:
    """The number of characters in a version, without loading its page."""
    if version is None:
        return 0
    return db.query(func.length(HorizonSandboxVersion.content)).filter(HorizonSandboxVersion.id == version.id).scalar() or 0


def list_versions(db: Session, sandbox: HorizonSandbox, *, limit: int, before: int | None = None) -> list[HorizonSandboxVersion]:
    query = db.query(HorizonSandboxVersion).filter(HorizonSandboxVersion.sandbox_id == sandbox.id)
    if before is not None:
        query = query.filter(HorizonSandboxVersion.number < before)
    return query.order_by(HorizonSandboxVersion.number.desc()).limit(limit).all()


def _clean_name(name: str | None) -> str:
    value = ' '.join(str(name or '').split())
    if not value:
        raise HTTPException(status_code=400, detail='Give the sandbox a name')
    return value


def _clean_text(value: str | None) -> str | None:
    text = str(value or '').strip()
    return text or None


def _unique_slug(db: Session, project_id: str, name: str, existing_id: str | None = None) -> str:
    base = slugify(name, 'sandbox')
    slug = base
    counter = 2
    while True:
        query = db.query(HorizonSandbox.id).filter(HorizonSandbox.project_id == project_id).filter(HorizonSandbox.slug == slug)
        if existing_id:
            query = query.filter(HorizonSandbox.id != existing_id)
        if query.first() is None:
            return slug
        slug = f'{base}-{counter}'
        counter += 1


def check_content(content: str) -> str:
    if '\x00' in content:
        raise HTTPException(status_code=400, detail='The page contains a NUL character. Remove it, then save again.')
    if len(content.encode('utf-8')) > MAX_CONTENT_BYTES:
        raise HTTPException(status_code=413, detail='The page is larger than 5 MB. Link large images instead of putting them in the page.')
    return content


def apply_edits(content: str, edits: list[tuple[str, str]]) -> str:
    """Replace text in the page. Each old text must be in the page exactly once."""
    for index, (old_text, new_text) in enumerate(edits, start=1):
        if not old_text:
            raise HTTPException(status_code=422, detail=f'Edit {index}: old_text is empty.')
        count = content.count(old_text)
        if count == 0:
            raise HTTPException(status_code=409, detail=f'Edit {index}: old_text is not in the page. Read the page again and copy the text exactly. Nothing was saved.')
        if count > 1:
            raise HTTPException(status_code=422, detail=f'Edit {index}: old_text is in the page {count} times. Add more of the text around it so that it matches once. Nothing was saved.')
        content = content.replace(old_text, new_text, 1)
    return content


def create_sandbox(db: Session, project_id: str, *, name: str, description: str | None, user: dict) -> HorizonSandbox:
    values = {'name': _clean_name(name), 'description': _clean_text(description)}
    now = time.time()

    def build() -> HorizonSandbox:
        sandbox = HorizonSandbox(
            id=str(uuid.uuid4()),
            project_id=project_id,
            latest_version=0,
            created_by=user.get('id') or user.get('username'),
            created_at=now,
            updated_at=now,
            **values,
        )
        db.add(sandbox)
        return sandbox

    return _commit_with_unique_slug(db, project_id, values['name'], build)


def update_sandbox(db: Session, sandbox: HorizonSandbox, *, name: str | None, description: str | None, fields: set[str]) -> HorizonSandbox:
    values = {'updated_at': time.time()}
    if 'name' in fields:
        values['name'] = _clean_name(name)
    if 'description' in fields:
        values['description'] = _clean_text(description)
    sandbox_id, project_id = sandbox.id, sandbox.project_id

    def apply() -> HorizonSandbox:
        record = db.get(HorizonSandbox, sandbox_id)
        for key, value in values.items():
            setattr(record, key, value)
        return record

    if 'name' not in fields:
        record = apply()
        db.commit()
        db.refresh(record)
        return record
    return _commit_with_unique_slug(db, project_id, values['name'], apply, existing_id=sandbox_id)


def _commit_with_unique_slug(db: Session, project_id: str, name: str, prepare, *, existing_id: str | None = None) -> HorizonSandbox:
    """Commit a new or renamed sandbox with a free slug.

    Two saves with the same name at the same time can pick the same slug. The
    unique constraint refuses the second one, which rolls back and tries again.
    """
    for _attempt in range(SLUG_ATTEMPTS):
        slug = _unique_slug(db, project_id, name, existing_id=existing_id)
        sandbox = prepare()
        sandbox.slug = slug
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(sandbox)
        return sandbox
    raise HTTPException(status_code=409, detail='Another sandbox got this name at the same time. Try again.')


def delete_sandbox(db: Session, sandbox: HorizonSandbox) -> None:
    """Delete the sandbox, its whole history and its share links."""
    db.query(HorizonSandboxVersion).filter(HorizonSandboxVersion.sandbox_id == sandbox.id).delete(synchronize_session=False)
    db.query(ShareLink).filter(ShareLink.share_type == 'sandbox').filter(ShareLink.sandbox_id == sandbox.id).delete(synchronize_session=False)
    db.delete(sandbox)
    db.commit()


def save_version(
    db: Session,
    sandbox: HorizonSandbox,
    content: str,
    *,
    user: dict,
    message: str | None = None,
    restored_from: int | None = None,
) -> tuple[HorizonSandboxVersion, bool]:
    """Save the page as the newest version.

    Returns the version and whether it is new. Content that is the same as
    the newest version does not add a version.
    """
    check_content(content)
    latest = get_version(db, sandbox)
    if latest is not None and latest.content == content:
        return latest, False
    agent = get_request_agent_identity()
    now = time.time()
    version = HorizonSandboxVersion(
        id=str(uuid.uuid4()),
        sandbox_id=sandbox.id,
        project_id=sandbox.project_id,
        number=sandbox.latest_version + 1,
        content=content,
        size_bytes=len(content.encode('utf-8')),
        message=_clean_text(message),
        restored_from=restored_from,
        author_id=user.get('id') or user.get('username'),
        author_name=user.get('display_name') or user.get('username'),
        agent_name=agent.get('name') if agent else None,
        created_at=now,
    )
    sandbox.latest_version = version.number
    sandbox.updated_at = now
    db.add(version)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Someone saved this sandbox at the same time. Read it again, then save your change.')
    db.refresh(version)
    return version, True


def _grouped_opcodes(codes: list[tuple], context: int):
    """Hunks of changes with `context` equal lines around them, as difflib groups them."""
    codes = list(codes) or [('equal', 0, 1, 0, 1)]
    if codes[0][0] == 'equal':
        tag, i1, i2, j1, j2 = codes[0]
        codes[0] = tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2
    if codes[-1][0] == 'equal':
        tag, i1, i2, j1, j2 = codes[-1]
        codes[-1] = tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)
    group = []
    for tag, i1, i2, j1, j2 in codes:
        if tag == 'equal' and i2 - i1 > context * 2:
            group.append((tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)))
            yield group
            group = []
            i1, j1 = max(i1, i2 - context), max(j1, j2 - context)
        group.append((tag, i1, i2, j1, j2))
    if group and not (len(group) == 1 and group[0][0] == 'equal'):
        yield group


def _line_opcodes(old_lines: list[str], new_lines: list[str]) -> list[tuple]:
    """Line changes from old to new, in bounded time.

    Most saves change one part of a page, so the equal start and end are
    found first. Only a short changed part gets full line matching.
    """
    shortest = min(len(old_lines), len(new_lines))
    start = 0
    while start < shortest and old_lines[start] == new_lines[start]:
        start += 1
    end = 0
    while end < shortest - start and old_lines[-1 - end] == new_lines[-1 - end]:
        end += 1
    old_mid = old_lines[start:len(old_lines) - end]
    new_mid = new_lines[start:len(new_lines) - end]
    if not old_mid and not new_mid:
        middle = []
    elif len(old_mid) <= DIFF_MATCH_MAX_LINES and len(new_mid) <= DIFF_MATCH_MAX_LINES:
        middle = difflib.SequenceMatcher(None, old_mid, new_mid).get_opcodes()
    elif not old_mid:
        middle = [('insert', 0, 0, 0, len(new_mid))]
    elif not new_mid:
        middle = [('delete', 0, len(old_mid), 0, 0)]
    else:
        middle = [('replace', 0, len(old_mid), 0, len(new_mid))]
    codes = [('equal', 0, start, 0, start)] if start else []
    codes.extend((tag, i1 + start, i2 + start, j1 + start, j2 + start) for tag, i1, i2, j1, j2 in middle)
    if end:
        codes.append(('equal', len(old_lines) - end, len(old_lines), len(new_lines) - end, len(new_lines)))
    return codes


def diff_versions(old_text: str, new_text: str, *, limit: int) -> dict:
    """Line differences from old_text to new_text, in hunks with context."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    codes = _line_opcodes(old_lines, new_lines)
    added = removed = 0
    for tag, i1, i2, j1, j2 in codes:
        if tag in ('replace', 'delete'):
            removed += i2 - i1
        if tag in ('replace', 'insert'):
            added += j2 - j1

    def line(kind: str, old: int | None, new: int | None, text: str) -> dict:
        if len(text) > DIFF_LINE_MAX_CHARS:
            text = f'{text[:DIFF_LINE_MAX_CHARS]}…'
        return {'kind': kind, 'old': old, 'new': new, 'text': text}

    hunks = []
    shown = 0
    truncated = False
    for group in _grouped_opcodes(codes, DIFF_CONTEXT_LINES):
        lines = []
        for tag, i1, i2, j1, j2 in group:
            if shown + len(lines) > limit:
                break
            if tag == 'equal':
                lines.extend(line(' ', i1 + k + 1, j1 + k + 1, old_lines[i1 + k]) for k in range(i2 - i1))
                continue
            lines.extend(line('-', i, None, old_lines[i - 1]) for i in range(i1 + 1, min(i2, i1 + limit) + 1))
            lines.extend(line('+', None, j, new_lines[j - 1]) for j in range(j1 + 1, min(j2, j1 + limit) + 1))
        if shown + len(lines) > limit or any(tag != 'equal' and (i2 - i1 > limit or j2 - j1 > limit) for tag, i1, i2, j1, j2 in group):
            lines = lines[:max(0, limit - shown)]
            truncated = True
        if lines:
            hunks.append({'old_start': group[0][1] + 1, 'new_start': group[0][3] + 1, 'lines': lines})
        shown += len(lines)
        if truncated:
            break
    return {'added': added, 'removed': removed, 'hunks': hunks, 'truncated': truncated}


def serialize_version(version: HorizonSandboxVersion | None) -> dict | None:
    if version is None:
        return None
    return {
        'number': version.number,
        'message': version.message or '',
        'restored_from': version.restored_from,
        'author_name': version.author_name or '',
        'agent_name': version.agent_name or '',
        'size_bytes': version.size_bytes,
        'created_at': version.created_at,
    }


def serialize_sandbox(sandbox: HorizonSandbox, version: HorizonSandboxVersion | None = None) -> dict:
    return {
        'id': sandbox.id,
        'project_id': sandbox.project_id,
        'slug': sandbox.slug,
        'name': sandbox.name,
        'description': sandbox.description or '',
        'type': 'sandbox',
        'latest_version': sandbox.latest_version,
        'created_by': sandbox.created_by,
        'created_at': sandbox.created_at,
        'updated_at': sandbox.updated_at,
        'version': serialize_version(version),
    }


def build_sandbox_content_item(sandbox: HorizonSandbox) -> dict:
    """The sandbox as an item of the project root listing."""
    return {
        'id': sandbox.id,
        'name': sandbox.name,
        'description': sandbox.description or '',
        'path': sandbox.slug,
        'slug': sandbox.slug,
        'type': 'sandbox',
        'source': 'horizons_db',
        'latest_version': sandbox.latest_version,
        'created_at': sandbox.created_at,
        'updated_at': sandbox.updated_at,
    }
