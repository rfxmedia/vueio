from __future__ import annotations

from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.horizon_pages import get_horizon_page_by_ref, page_allows_path, page_zip_resource_paths
from app.services.project_link_content import collect_project_virtual_zip_entries
from app.services.horizons.projects import get_horizon_project
from app.services.horizons.version_publication import held_media_paths_for_project
from app.services.projects import get_project_dir, resolve_project_root
from app.services.share_access import build_shared_file_info_payload, normalize_virtual_path, require_path_within_shared_root, resolve_shared_media_target
from app.services.zip_utils import ZipEntry

from app.services._project_content_gateway_impl import (
    AuthorizedZipRequest,
    ContentListResult,
    ContentRef,
    ResolvedContent,
    _list_shared_project_contents,
    resolve_horizons_object_share,
    settings,
)


class SharedMediaPolicy:
    name = 'shared_media'

    def __init__(self, db: Session, share):
        self.db = db
        self.share = share

    def normalize_request_path(self, raw_path: str | None, *, allow_empty: bool = True) -> str:
        try:
            return normalize_virtual_path(raw_path, allow_empty=allow_empty)
        except HTTPException as exc:
            if self.share.share_type in {'folder', 'project-folder'}:
                raise HTTPException(status_code=403, detail='Access denied - path outside shared folder') from exc
            raise

    def assert_can_list(self, path: str) -> None:
        raise NotImplementedError

    def assert_can_resolve(self, ref: ContentRef, *, purpose: Literal['metadata', 'stream', 'thumbnail', 'download', 'zip']) -> ContentRef:
        return ref

    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]:
        raise NotImplementedError

    def list_folder(self, path: str, *, include_counts: bool = False) -> ContentListResult:
        raise NotImplementedError

    def resolve(self, ref: ContentRef, *, purpose: str) -> ResolvedContent:
        requested = self.normalize_request_path(ref.path or self.share.path or '', allow_empty=True)
        full_path, cache_key = resolve_shared_media_target(self.share, requested, db=self.db, media_asset_id=ref.media_asset_id)
        payload = build_shared_file_info_payload(self.share, requested, self.db, media_asset_id=ref.media_asset_id)
        return ResolvedContent(
            ref,
            full_path,
            bool(full_path and full_path.exists()),
            cache_key,
            None,
            media_asset_id=ref.media_asset_id,
            canonical_path=payload.get('path') or requested,
            physical_root=(resolve_project_root(get_horizon_project(self.db, self.share.project_id)) if self.share.project_id else settings.MEDIA_ROOT),
            payload=payload,
        )

    def collect_zip_entries(self, request: AuthorizedZipRequest) -> list[ZipEntry]:
        raise NotImplementedError


class SharedProjectPolicy:
    name = 'shared_project'

    def __init__(self, db: Session, share):
        self.db = db
        self.share = share
        self.project_id = share.project_id

    def normalize_request_path(self, raw_path: str | None, *, allow_empty: bool = True) -> str:
        return normalize_virtual_path(raw_path, allow_empty=allow_empty)

    def assert_can_list(self, path: str) -> None:
        return None

    def assert_can_resolve(self, ref: ContentRef, *, purpose: Literal['metadata', 'stream', 'thumbnail', 'download', 'zip']) -> ContentRef:
        return ref

    def resolve(self, ref: ContentRef, *, purpose: str) -> ResolvedContent:
        if ref.media_asset_id or ref.shot_version_id:
            return resolve_horizons_object_share(self.share, self.db, asset_id=ref.media_asset_id, version_id=ref.shot_version_id)
        return SharedMediaPolicy(self.db, self.share).resolve(ref, purpose=purpose)

    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]:
        if self.share.share_type == 'page':
            page = get_horizon_page_by_ref(self.db, self.share.project_id, self.share.page_id or '')
            refs: list[ContentRef] = []
            for raw in raw_paths:
                requested = self.normalize_request_path(raw, allow_empty=True)
                authorized_paths = page_zip_resource_paths(page, requested)
                if not authorized_paths:
                    raise HTTPException(status_code=403, detail='This page does not grant access to the requested file')
                refs.extend(ContentRef(namespace='page_resource', project_id=self.share.project_id, path=path, share_id=self.share.id, page_id=self.share.page_id) for path in authorized_paths)
            return refs
        return [ContentRef(namespace='horizons_project', project_id=self.share.project_id, path=self.normalize_request_path(path, allow_empty=True), share_id=self.share.id) for path in raw_paths]

    def list_folder(self, path: str, *, include_counts: bool = False) -> ContentListResult:
        normalized = self.normalize_request_path(path, allow_empty=True)
        if self.share.share_type == 'page':
            page = get_horizon_page_by_ref(self.db, self.share.project_id, self.share.page_id or '')
            if not normalized or not page_allows_path(page, normalized):
                raise HTTPException(status_code=403, detail='Access denied - path is not referenced by this page')
        return _list_shared_project_contents(self.db, self.share, normalized, include_counts=include_counts)

    def collect_zip_entries(self, request: AuthorizedZipRequest) -> list[ZipEntry]:
        held_paths = held_media_paths_for_project(self.db, self.project_id)
        entries: list[ZipEntry] = []
        for ref in request.refs:
            entries.extend(collect_project_virtual_zip_entries(
                self.project_id,
                [ref.path],
                db=self.db,
                budget=request.budget,
                discovered_identities=request.discovered_identities,
                excluded_paths=held_paths,
            ))
        return entries


class SharedProjectFolderPolicy(SharedProjectPolicy):
    name = 'shared_project_folder'

    def normalize_request_path(self, raw_path: str | None, *, allow_empty: bool = True) -> str:
        try:
            return normalize_virtual_path(raw_path, allow_empty=allow_empty)
        except HTTPException as exc:
            raise HTTPException(status_code=403, detail='Access denied - path outside shared folder') from exc

    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]:
        for candidate in raw_paths:
            require_path_within_shared_root(self.share.path or '', candidate or self.share.path or '')
        return [ContentRef(namespace='horizons_project', project_id=self.share.project_id, path=self.share.path or '', share_id=self.share.id, is_folder=True)]

    def list_folder(self, path: str, *, include_counts: bool = False) -> ContentListResult:
        normalized = self.normalize_request_path(path, allow_empty=True)
        base_path = (self.share.path or '').strip('/')
        if normalized:
            normalized = require_path_within_shared_root(base_path, normalized)
        return _list_shared_project_contents(self.db, self.share, normalized or base_path, include_counts=include_counts)


class SharedProjectFilePolicy(SharedProjectPolicy):
    name = 'shared_project_file'

    def assert_can_zip_roots(self, raw_paths: list[str]) -> list[ContentRef]:
        shared_file = normalize_virtual_path(self.share.path, allow_empty=False)
        refs = []
        for raw in raw_paths:
            if normalize_virtual_path(raw or self.share.path or '', allow_empty=True) != shared_file:
                raise HTTPException(status_code=403, detail='Access denied - can only access shared file')
            refs.append(ContentRef(namespace='horizons_project', project_id=self.share.project_id, path=shared_file, share_id=self.share.id, is_folder=False))
        return refs


class SharedPagePolicy(SharedProjectPolicy):
    name = 'shared_page'
