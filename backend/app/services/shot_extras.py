"""Changes to the extras of a shot, recorded in tracker history."""
from __future__ import annotations

import time
import uuid

from fastapi import HTTPException

from app.models import HorizonShot, HorizonShotExtra, HorizonShotExtraFile, HorizonShotVersion, MediaAsset
from app.services.horizons.extras import MAX_EXTRAS_PER_SHOT, normalize_extra_name, normalize_extra_note
from app.services.horizons.projects import require_horizon_project_writable
from app.services.media_assets import register_media_asset
from app.services.shot_command_base import ShotCommandBase
from app.services.shot_command_types import ShotCommandContext, ShotCommandResult


class ShotExtrasService(ShotCommandBase):
    """Tracker-history-aware changes to the extras of a shot."""

    def __init__(self, db):
        super().__init__(db)
        # Files that need a thumbnail after the change commits.
        self._queued_paths: list[str] = []

    def _result(self, shot: HorizonShot) -> ShotCommandResult:
        return ShotCommandResult(shots=[shot], queued_media_paths=list(self._queued_paths))

    def _begin(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot) -> HorizonShot:
        if not ctx.can_update_shot:
            raise HTTPException(status_code=403, detail='Editor access required')
        require_horizon_project_writable(self.db, ctx.project_id)
        self._lock_history(ctx)
        return self._shot(ctx, shot_ref)

    def _require_manager(self, ctx: ShotCommandContext, detail: str = 'Members with review access can add files to extras, but cannot change or remove extras') -> None:
        if ctx.restricted_artist:
            raise HTTPException(status_code=403, detail=detail)

    def _version(self, shot: HorizonShot, version_id: str | None) -> HorizonShotVersion:
        query = self.db.query(HorizonShotVersion).filter(HorizonShotVersion.shot_id == shot.id)
        if version_id:
            version = query.filter(HorizonShotVersion.id == version_id).first()
        else:
            version = query.order_by(HorizonShotVersion.created_at.desc(), HorizonShotVersion.id.desc()).first()
        if version is None:
            raise HTTPException(status_code=404 if version_id else 409, detail='Version not found' if version_id else 'Add a version to this shot first')
        return version

    def _extra(self, shot: HorizonShot, extra_id: str) -> HorizonShotExtra:
        extra = self.db.query(HorizonShotExtra).filter(HorizonShotExtra.id == extra_id, HorizonShotExtra.shot_id == shot.id).first()
        if extra is None:
            raise HTTPException(status_code=404, detail='Extra not found')
        return extra

    def _asset(self, ctx: ShotCommandContext, shot: HorizonShot, extra: HorizonShotExtra | None, *,
               file_path: str | None, media_asset_id: str | None, from_version_id: str | None) -> MediaAsset:
        if sum(bool(value) for value in (file_path, media_asset_id, from_version_id)) != 1:
            raise HTTPException(status_code=400, detail='Choose one file: a project file, a media asset or an earlier version')
        if file_path:
            normalized = self._validate_media_path(ctx, file_path, any_file=True)
            asset = register_media_asset(self.db, ctx.project_id, normalized, storage_scope='tracker_version', commit=False)
            if asset is None:
                raise HTTPException(status_code=404, detail='File not found')
            return asset
        if from_version_id:
            source = None
            if extra is not None:
                source = (
                    self.db.query(HorizonShotExtraFile)
                    .filter(HorizonShotExtraFile.extra_id == extra.id, HorizonShotExtraFile.version_id == from_version_id)
                    .first()
                )
            if source is None:
                raise HTTPException(status_code=404, detail='That version has no file for this extra')
            media_asset_id = source.media_asset_id
        asset = self._media_asset(ctx, media_asset_id)
        if asset is None or asset.unavailable_at is not None:
            raise HTTPException(status_code=409, detail='This file is offline. Choose another file.')
        return asset

    def _put_file(self, ctx: ShotCommandContext, shot: HorizonShot, extra: HorizonShotExtra, version: HorizonShotVersion,
                  asset: MediaAsset, created_by: str | None) -> bool:
        now = time.time()
        row = (
            self.db.query(HorizonShotExtraFile)
            .filter(HorizonShotExtraFile.extra_id == extra.id, HorizonShotExtraFile.version_id == version.id)
            .first()
        )
        replaced = row is not None
        if row is None:
            row = HorizonShotExtraFile(
                id=str(uuid.uuid4()), project_id=ctx.project_id, tracker_id=ctx.tracker_id, shot_id=shot.id,
                extra_id=extra.id, version_id=version.id, created_at=now,
            )
            self.db.add(row)
        row.media_asset_id = asset.id
        row.created_by = created_by
        row.updated_at = now
        self._queued_paths.append(asset.file_path)
        return replaced

    def _event_payload(self, shot: HorizonShot, extra: HorizonShotExtra, version: HorizonShotVersion | None = None, **extra_fields) -> dict:
        payload = {'shot_id': shot.id, 'shot_code': shot.shot_code, 'extra_id': extra.id, 'extra_name': extra.name, **extra_fields}
        if version is not None:
            payload['version_label'] = version.label
        return payload

    def add_extra(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, *, name: str, note: str | None = None,
                  client_visible: bool = True, version_id: str | None = None, file_path: str | None = None,
                  media_asset_id: str | None = None, created_by: str | None = None) -> tuple[ShotCommandResult, HorizonShotExtra]:
        shot = self._begin(ctx, shot_ref)
        has_file = bool(file_path or media_asset_id)
        if not has_file:
            # Asking for an extra is the team's decision, not the artist's.
            self._require_manager(ctx, 'Members with review access can only add an extra with a file')
        existing = self.db.query(HorizonShotExtra).filter(HorizonShotExtra.shot_id == shot.id).all()
        if len(existing) >= MAX_EXTRAS_PER_SHOT:
            raise HTTPException(status_code=400, detail=f'A shot can have {MAX_EXTRAS_PER_SHOT} extras at most')
        version = self._version(shot, version_id) if has_file or version_id else None
        asset = self._asset(ctx, shot, None, file_path=file_path, media_asset_id=media_asset_id, from_version_id=None) if has_file else None
        now = time.time()
        extra = HorizonShotExtra(
            id=str(uuid.uuid4()), project_id=ctx.project_id, tracker_id=ctx.tracker_id, shot_id=shot.id,
            name=normalize_extra_name(name), note=normalize_extra_note(note), client_visible=bool(client_visible),
            sort_order=max((item.sort_order for item in existing), default=-1) + 1,
            created_by=created_by, created_at=now, updated_at=now,
        )
        self.db.add(extra)
        self.db.flush()
        if asset is not None and version is not None:
            self._put_file(ctx, shot, extra, version, asset, created_by)
        self._touch(ctx, shot)
        result = self._result(shot)
        self._emit(result, ctx, 'extra_added', shot=shot, version=version if asset else None,
                   payload=self._event_payload(shot, extra, version if asset else None, needed=asset is None))
        return result, extra

    def update_extra(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, extra_id: str, *, fields: set[str],
                     name: str | None = None, note: str | None = None, client_visible: bool | None = None) -> tuple[ShotCommandResult, HorizonShotExtra]:
        shot = self._begin(ctx, shot_ref)
        self._require_manager(ctx)
        extra = self._extra(shot, extra_id)
        old_name = extra.name
        if 'name' in fields:
            extra.name = normalize_extra_name(name)
        if 'note' in fields:
            extra.note = normalize_extra_note(note)
        if 'client_visible' in fields and client_visible is not None:
            extra.client_visible = bool(client_visible)
        extra.updated_at = time.time()
        self._touch(ctx, shot)
        result = self._result(shot)
        self._emit(result, ctx, 'extra_changed', shot=shot, payload=self._event_payload(
            shot, extra, old_name=old_name if extra.name != old_name else None, client_visible=bool(extra.client_visible)))
        return result, extra

    def reorder_extras(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, extra_ids: list[str]) -> ShotCommandResult:
        shot = self._begin(ctx, shot_ref)
        self._require_manager(ctx)
        extras = {extra.id: extra for extra in self.db.query(HorizonShotExtra).filter(HorizonShotExtra.shot_id == shot.id).all()}
        if len(extra_ids) != len(set(extra_ids)) or set(extra_ids) != set(extras):
            raise HTTPException(status_code=400, detail='Send every extra of the shot once, in the new order')
        now = time.time()
        for index, extra_id in enumerate(extra_ids):
            extras[extra_id].sort_order = index
            extras[extra_id].updated_at = now
        self._touch(ctx, shot)
        result = self._result(shot)
        self._emit(result, ctx, 'extra_changed', shot=shot, payload={'shot_id': shot.id, 'shot_code': shot.shot_code, 'reordered': True})
        return result

    def remove_extra(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, extra_id: str) -> ShotCommandResult:
        shot = self._begin(ctx, shot_ref)
        self._require_manager(ctx)
        extra = self._extra(shot, extra_id)
        payload = self._event_payload(shot, extra)
        self.db.query(HorizonShotExtraFile).filter(HorizonShotExtraFile.extra_id == extra.id).delete(synchronize_session=False)
        self.db.delete(extra)
        self.db.flush()
        self._touch(ctx, shot)
        result = self._result(shot)
        self._emit(result, ctx, 'extra_removed', shot=shot, payload=payload)
        return result

    def set_file(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, extra_id: str, version_id: str, *,
                 file_path: str | None = None, media_asset_id: str | None = None, from_version_id: str | None = None,
                 created_by: str | None = None) -> tuple[ShotCommandResult, HorizonShotExtraFile]:
        shot = self._begin(ctx, shot_ref)
        extra = self._extra(shot, extra_id)
        version = self._version(shot, version_id)
        if from_version_id == version.id:
            raise HTTPException(status_code=400, detail='Choose an earlier version')
        asset = self._asset(ctx, shot, extra, file_path=file_path, media_asset_id=media_asset_id, from_version_id=from_version_id)
        replaced = self._put_file(ctx, shot, extra, version, asset, created_by)
        self.db.flush()
        self._touch(ctx, shot)
        result = self._result(shot)
        self._emit(result, ctx, 'extra_file_set', shot=shot, version=version,
                   payload=self._event_payload(shot, extra, version, replaced=replaced))
        row = (
            self.db.query(HorizonShotExtraFile)
            .filter(HorizonShotExtraFile.extra_id == extra.id, HorizonShotExtraFile.version_id == version.id)
            .one()
        )
        return result, row

    def clear_file(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, extra_id: str, version_id: str) -> ShotCommandResult:
        shot = self._begin(ctx, shot_ref)
        self._require_manager(ctx)
        extra = self._extra(shot, extra_id)
        version = self._version(shot, version_id)
        deleted = (
            self.db.query(HorizonShotExtraFile)
            .filter(HorizonShotExtraFile.extra_id == extra.id, HorizonShotExtraFile.version_id == version.id)
            .delete(synchronize_session=False)
        )
        if not deleted:
            raise HTTPException(status_code=404, detail='This version has no file for this extra')
        self._touch(ctx, shot)
        result = self._result(shot)
        self._emit(result, ctx, 'extra_file_cleared', shot=shot, version=version, payload=self._event_payload(shot, extra, version))
        return result
