from __future__ import annotations

import json
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    Comment,
    HorizonPage,
    HorizonProject,
    MediaAsset,
    MediaMetadata,
    ShareLink,
    ShotRegistryEntry,
    UploadItem,
    UploadSession,
    VersionRegistryEntry,
)


def rewrite_path(value: str | None, old_path: str, new_path: str) -> str | None:
    """Rewrite one exact project path or a descendant of it."""
    value_text = str(value or '').strip().strip('/')
    old_text = str(old_path or '').strip().strip('/')
    new_text = str(new_path or '').strip().strip('/')
    if not value_text or not old_text or not new_text:
        return value
    if value_text == old_text:
        return new_text
    prefix = f'{old_text}/'
    if value_text.startswith(prefix):
        return f'{new_text}/{value_text[len(prefix):]}'
    return value


def rewrite_project_links_payload(
    payload: dict | None,
    *,
    old_path: str,
    new_path: str,
) -> tuple[dict, int]:
    """Rewrite project-owned link sources without changing virtual placement."""
    source = payload if isinstance(payload, dict) else {}
    links = source.get('links')
    if not isinstance(links, list):
        return source, 0
    changed = 0
    rewritten_links = []
    for raw_link in links:
        link = dict(raw_link) if isinstance(raw_link, dict) else raw_link
        if isinstance(link, dict) and link.get('storage_scope') == 'project':
            rewritten = rewrite_path(link.get('source_path'), old_path, new_path)
            if rewritten != link.get('source_path'):
                link['source_path'] = rewritten
                changed += 1
        rewritten_links.append(link)
    if not changed:
        return source, 0
    return {**source, 'links': rewritten_links}, changed


def _rewrite_page_blocks(raw: str | None, old_path: str, new_path: str) -> tuple[str | None, int]:
    try:
        blocks = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return raw, 0
    if not isinstance(blocks, list):
        return raw, 0
    changed = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get('type')
        if block_type == 'resource_list':
            resources = block.get('resources')
            if not isinstance(resources, list):
                continue
            for resource in resources:
                if not isinstance(resource, dict) or resource.get('kind') not in {'file', 'folder'}:
                    continue
                rewritten = rewrite_path(resource.get('path'), old_path, new_path)
                if rewritten != resource.get('path'):
                    resource['path'] = rewritten
                    changed += 1
        elif block_type == 'upload_inbox':
            rewritten = rewrite_path(block.get('target_path'), old_path, new_path)
            if rewritten != block.get('target_path'):
                block['target_path'] = rewritten
                changed += 1
    return (
        json.dumps(blocks, separators=(',', ':')) if changed else raw,
        changed,
    )


def _rewrite_comment_attachments(raw: str | None, old_path: str, new_path: str) -> tuple[str | None, int]:
    try:
        attachments = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return raw, 0
    if not isinstance(attachments, list):
        return raw, 0
    changed = 0
    for attachment in attachments:
        if (
            not isinstance(attachment, dict)
            or attachment.get('attachment_type') == 'reference'
            or attachment.get('scope') != 'project'
        ):
            continue
        rewritten = rewrite_path(attachment.get('rel_path'), old_path, new_path)
        if rewritten != attachment.get('rel_path'):
            attachment['rel_path'] = rewritten
            changed += 1
    return (
        json.dumps(attachments, separators=(',', ':')) if changed else raw,
        changed,
    )


def rewrite_project_path_references(
    db: Session,
    project_id: str,
    old_path: str,
    new_path: str,
    *,
    moved_is_folder: bool = False,
    commit: bool = True,
) -> dict[str, int]:
    """Update persisted project-path references in the caller's transaction."""
    counts = {
        'shares': 0,
        'project_thumbnails': 0,
        'page_covers': 0,
        'page_blocks': 0,
        'comments': 0,
        'comment_attachments': 0,
        'media_metadata': 0,
        'upload_sessions': 0,
        'upload_items': 0,
        'version_registry': 0,
        'shot_registry': 0,
    }
    now = time.time()

    project = db.get(HorizonProject, project_id)
    if project is not None:
        rewritten = rewrite_path(project.thumbnail_path, old_path, new_path)
        if rewritten != project.thumbnail_path:
            project.thumbnail_path = rewritten
            project.updated_at = now
            db.add(project)
            counts['project_thumbnails'] += 1

    for share in (
        db.query(ShareLink)
        .filter(ShareLink.project_id == project_id)
        .filter(ShareLink.share_type.in_(('file', 'folder', 'project-file', 'project-folder')))
        .all()
    ):
        rewritten = rewrite_path(share.path, old_path, new_path)
        if rewritten != share.path:
            share.path = rewritten
            db.add(share)
            counts['shares'] += 1

    for page in db.query(HorizonPage).filter(HorizonPage.project_id == project_id).all():
        page_changed = False
        rewritten_cover = rewrite_path(page.cover_path, old_path, new_path)
        if rewritten_cover != page.cover_path:
            page.cover_path = rewritten_cover
            counts['page_covers'] += 1
            page_changed = True
        rewritten_blocks, block_count = _rewrite_page_blocks(
            page.blocks_json,
            old_path,
            new_path,
        )
        if block_count:
            page.blocks_json = rewritten_blocks
            counts['page_blocks'] += block_count
            page_changed = True
        if page_changed:
            page.updated_at = now
            db.add(page)

    for comment in db.query(Comment).filter(Comment.project_id == project_id).all():
        comment_changed = False
        rewritten_comment_path = rewrite_path(comment.file_path, old_path, new_path)
        if rewritten_comment_path != comment.file_path:
            comment.file_path = rewritten_comment_path
            counts['comments'] += 1
            comment_changed = True
        rewritten_attachments, attachment_count = _rewrite_comment_attachments(
            comment.attachments_data,
            old_path,
            new_path,
        )
        if attachment_count:
            comment.attachments_data = rewritten_attachments
            counts['comment_attachments'] += attachment_count
            comment_changed = True
        if comment_changed:
            db.add(comment)

    project_asset_ids = [
        row[0]
        for row in (
            db.query(MediaAsset.id)
            .filter(MediaAsset.project_id == project_id)
            .filter(MediaAsset.storage_scope == 'project')
            .all()
        )
    ]
    if project_asset_ids:
        for metadata in (
            db.query(MediaMetadata)
            .filter(MediaMetadata.media_asset_id.in_(project_asset_ids))
            .all()
        ):
            rewritten = rewrite_path(metadata.file_path, old_path, new_path)
            if rewritten != metadata.file_path:
                metadata.file_path = rewritten
                metadata.updated_at = now
                db.add(metadata)
                counts['media_metadata'] += 1

    upload_sessions = (
        db.query(UploadSession)
        .filter(UploadSession.project_id == project_id)
        .all()
    )
    upload_session_ids = [session.id for session in upload_sessions]
    if moved_is_folder:
        for session in upload_sessions:
            rewritten = rewrite_path(session.base_path, old_path, new_path)
            if rewritten != session.base_path:
                session.base_path = rewritten
                session.updated_at = now
                db.add(session)
                counts['upload_sessions'] += 1
    if upload_session_ids:
        project_root = None
        for item in (
            db.query(UploadItem)
            .filter(UploadItem.session_id.in_(upload_session_ids))
            .all()
        ):
            item_changed = False
            if moved_is_folder or item.status == 'complete':
                rewritten = rewrite_path(item.final_path, old_path, new_path)
                if rewritten != item.final_path:
                    item.final_path = rewritten
                    item_changed = True
            if moved_is_folder and item.temp_path and project is not None:
                if project_root is None:
                    from app.services.horizons.projects import resolve_project_root

                    project_root = resolve_project_root(project)
                try:
                    relative_temp = str(
                        Path(item.temp_path)
                        .resolve(strict=False)
                        .relative_to(project_root.resolve(strict=False))
                    )
                except (OSError, ValueError):
                    relative_temp = ''
                rewritten_temp = rewrite_path(relative_temp, old_path, new_path)
                if rewritten_temp and rewritten_temp != relative_temp:
                    item.temp_path = str(project_root / rewritten_temp)
                    item_changed = True
            if item_changed:
                item.updated_at = now
                db.add(item)
                counts['upload_items'] += 1

    for entry in db.query(VersionRegistryEntry).filter(VersionRegistryEntry.project_id == project_id).all():
        rewritten = rewrite_path(entry.file_path, old_path, new_path)
        if rewritten != entry.file_path:
            entry.file_path = rewritten
            entry.updated_at = now
            db.add(entry)
            counts['version_registry'] += 1

    for entry in db.query(ShotRegistryEntry).filter(ShotRegistryEntry.project_id == project_id).all():
        rewritten = rewrite_path(entry.latest_file_path, old_path, new_path)
        if rewritten != entry.latest_file_path:
            entry.latest_file_path = rewritten
            entry.updated_at = now
            db.add(entry)
            counts['shot_registry'] += 1

    if commit:
        db.commit()
    else:
        db.flush()
    return counts
