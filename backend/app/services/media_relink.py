"""Shared, read-only file matching for folder changes and media recovery."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from fastapi import HTTPException

from app.config import get_settings
from app.models import MediaAsset
from app.services.media_assets import content_fingerprint, file_matches_content_identity, read_content_identity
from app.services.media_resolution import source_signature, stored_media_asset_cache_identity


def contained_file(root: Path, relative: str) -> Path | None:
    normalized = str(relative or '').replace('\\', '/')
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith('/') or any(part in {'.', '..'} for part in parts):
        return None
    try:
        target = (root / normalized).resolve()
        target.relative_to(root.resolve())
        return target
    except (OSError, RuntimeError, ValueError):
        return None


class MediaRelinkMatcher:
    """Try known paths first; index and fingerprint fallback candidates once."""

    def __init__(self, root: Path, search_root: Path | None = None):
        self.root = root.resolve()
        self.search_root = (search_root or root).resolve()
        if not self.search_root.is_relative_to(self.root):
            raise HTTPException(status_code=400, detail='Search folder must be inside the project folder.')
        self.files_by_size: dict[int, list[str]] | None = None
        self.identities: dict[tuple[str, str, str], str] = {}

    def _identity_matches(self, target: Path, expected: str) -> bool:
        signature = source_signature(target)
        normalized = expected.strip().lower()
        kind = normalized.split(':', 1)[0] if ':' in normalized else 'sha256'
        key = (str(target), signature, kind)
        if key not in self.identities:
            identity = read_content_identity(target, normalized)
            if identity is not None:
                self.identities[key] = identity
        if source_signature(target) != signature:
            raise HTTPException(status_code=409, detail='A file is still changing. Let the copy or save finish, then check the folder again.')
        return self.identities.get(key) == normalized

    def _index(self) -> dict[int, list[str]]:
        if self.files_by_size is not None:
            return self.files_by_size
        result: dict[int, list[str]] = {}
        count = 0
        limit = get_settings().SEARCH_INDEX_MAX_FILES

        def unreadable(_error):
            raise HTTPException(status_code=409, detail='Part of this folder could not be read. Check drive access, then try again.')

        for directory, subdirectories, filenames in os.walk(self.search_root, followlinks=False, onerror=unreadable):
            parent = Path(directory)
            subdirectories[:] = sorted(name for name in subdirectories if not (parent / name).is_symlink())
            for name in sorted(filenames):
                count += 1
                if count > limit:
                    raise HTTPException(status_code=409, detail='This folder is too large to search safely. Choose a smaller folder that contains the missing media.')
                target = parent / name
                if target.is_symlink():
                    continue
                try:
                    if not target.is_file():
                        continue
                    relative = target.resolve().relative_to(self.root).as_posix()
                    result.setdefault(target.stat().st_size, []).append(relative)
                except FileNotFoundError:
                    raise HTTPException(status_code=409, detail='The folder changed during the check. Let the move finish, then try again.')
                except (OSError, ValueError):
                    unreadable(None)
        self.files_by_size = result
        return result

    def match(self, asset: MediaAsset, candidates: list[str]) -> tuple[dict | None, dict | None]:
        source = str(asset.file_path or '').replace('\\', '/').strip('/')
        expected_size = asset.file_size
        identity = str(asset.content_hash or '')
        issue = 'not_found'
        matches: list[str] = []
        try:
            for relative in candidates:
                target = contained_file(self.root, relative)
                if target is None:
                    issue = 'invalid_path'
                    continue
                if not target.is_file():
                    continue
                if expected_size is not None and target.stat().st_size != expected_size:
                    issue = 'size_mismatch'
                    continue
                if identity:
                    if not self._identity_matches(target, identity):
                        issue = 'content_mismatch'
                        continue
                elif relative != source or expected_size is None:
                    # A filename or suffix alone cannot establish an old identity.
                    issue = 'identity_unavailable'
                    continue
                matches.append(relative)
                if relative == source:
                    matches = [relative]
                    break

            if not matches and identity and expected_size is not None:
                for relative in self._index().get(expected_size, []):
                    target = contained_file(self.root, relative)
                    if target is not None and self._identity_matches(target, identity):
                        matches.append(relative)
            if len(matches) == 1:
                relative = matches[0]
                target = contained_file(self.root, relative)
                return {
                    'asset_id': asset.id, 'path': relative, 'source_path': asset.file_path, 'source_scope': asset.storage_scope,
                    'size': target.stat().st_size, 'signature': source_signature(target),
                    'legacy_rebased': asset.storage_scope == 'media_root' and relative != source,
                }, None
        except OSError as exc:
            raise HTTPException(status_code=409, detail='A file could not be read. Check the drive connection and folder access, then try again.') from exc
        return None, {
            'asset_id': asset.id, 'path': asset.file_path, 'source_path': asset.file_path,
            'reason': 'ambiguous_match' if len(matches) > 1 else issue,
            **({'candidates': matches} if len(matches) > 1 else {}),
        }


def apply_media_match(asset: MediaAsset, root: Path, match: dict, now: float) -> None:
    """Recheck the planned identity before changing metadata. Never write media."""
    target = contained_file(root, match['path'])
    try:
        if target is None or not target.is_file():
            raise ValueError('File missing')
        before = source_signature(target)
        if before != match['signature'] or target.stat().st_size != match['size']:
            raise ValueError('File changed')
        if asset.content_hash and not file_matches_content_identity(target, asset.content_hash):
            raise ValueError('File changed')
        identity = asset.content_hash or content_fingerprint(target)
        stat = target.stat()
        if not identity or before != source_signature(target):
            raise ValueError('File changed')
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail='A file changed after it was checked. Nothing was relinked. Check the folder again.') from exc
    if not asset.artifact_identity:
        asset.artifact_identity = stored_media_asset_cache_identity(asset)
    asset.file_path = match['path']
    asset.storage_scope = 'project'
    asset.source_signature = before
    asset.content_hash = identity
    asset.file_size = stat.st_size
    asset.modified_at = stat.st_mtime
    asset.unavailable_at = None
    asset.unavailable_reason = None
    asset.updated_at = now


def relocation_plan_id(project, plan: dict) -> str:
    payload = [project.storage_root, project.storage_path, plan]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require_reviewed_plan(plan: dict, expected_plan_id: str | None) -> None:
    if expected_plan_id is not None and expected_plan_id != plan.get('plan_id'):
        raise HTTPException(status_code=409, detail='The project or folder changed after your check. Nothing was relinked. Check the folder again.')
