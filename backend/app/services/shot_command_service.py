from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
import time
import uuid

from fastapi import HTTPException

from app.models import HorizonShot, HorizonShotVersion, HorizonTracker, MediaAsset
from app.services.horizons.shots import (
    _create_horizon_shot_no_commit,
    _create_horizon_shot_version_no_commit,
    _update_horizon_shot_no_commit,
    _update_horizon_shot_version_no_commit,
    list_horizon_shot_versions,
    set_horizon_shot_assignees,
)
from app.services.horizons.team import (
    get_horizon_shot_assignee_ids,
    serialize_horizon_shot_assignees,
)
from app.services.horizons.projects import require_horizon_project_writable
from app.services.horizons.version_publication import (
    initial_version_publication,
    move_latest_published_version_to_review,
    set_version_share_state,
    version_is_published,
    version_media_is_publishable,
)
from app.services.media import get_safe_path, is_image, is_video
from app.services.media_assets import register_media_asset
from app.services.media_resolution import resolve_media_target
from app.services.shot_command_base import ShotCommandBase
from app.services.shot_command_types import ShotCommandContext, ShotCommandResult
from app.services.shot_command_utils import next_version_label, normalize_bulk_shot_refs, normalize_shot_status


class ShotCommandService(ShotCommandBase):
    def _require_update_shot(self, ctx: ShotCommandContext) -> None:
        if not ctx.can_update_shot:
            raise HTTPException(status_code=403, detail='Editor access required')

    def _move_published_version_to_review(
        self,
        result: ShotCommandResult,
        ctx: ShotCommandContext,
        shot: HorizonShot,
        version: HorizonShotVersion,
    ) -> str | None:
        previous_status = move_latest_published_version_to_review(self.db, shot, version)
        if previous_status is None:
            return None
        result.stats_dirty_tracker_ids.add(ctx.tracker_id)
        result.activity_records.append({
            'type': 'status_change',
            'entity_type': 'shot',
            'entity_id': shot.id,
            'entity_name': shot.shot_code,
            'tracker_name': ctx.tracker_name,
            'old_status': previous_status,
            'new_status': shot.status,
        })
        result.response_hint.update({
            'shot_status_changed': True,
            'previous_shot_status': previous_status,
            'shot_status': shot.status,
        })
        return previous_status

    def create_shot(self, ctx: ShotCommandContext, *, shot_code: str, description: str | None = None, status: str | None = None, category: str | None = None, assignee_user_id: str | None = None, assignee_user_ids: list[str | None] | None = None) -> ShotCommandResult:
        if not ctx.can_create_shot or ctx.restricted_artist:
            raise HTTPException(status_code=403, detail='Artists cannot create tracker shots')
        self._lock_history(ctx)
        shot = _create_horizon_shot_no_commit(
            self.db,
            project_id=ctx.project_id,
            tracker_id=ctx.tracker_id,
            shot_code=shot_code,
            description=description,
            status=status,
            category=category,
            assignee_user_id=assignee_user_id,
            assignee_user_ids=assignee_user_ids,
        )
        result = ShotCommandResult(shots=[shot], stats_dirty_tracker_ids={ctx.tracker_id})
        payload = {'shot_id': shot.id, 'shot_code': shot.shot_code, 'status': shot.status}
        if ctx.actor.source == 'app':
            payload['tag'] = shot.category
        self._emit(result, ctx, 'shot_created', shot=shot, payload=payload)
        return result

    def update_shot(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, *, fields_set: set[str], shot_code: str | None = None, description: str | None = None, status: str | None = None, category: str | None = None, assignee_user_id: str | None = None, assignee_user_ids: list[str | None] | None = None) -> ShotCommandResult:
        self._require_update_shot(ctx)
        fields = set(fields_set or set())
        if ctx.restricted_artist and fields - {'status', 'category'}:
            raise HTTPException(status_code=403, detail='Artists can only update assigned shot status and tag')
        self._lock_history(ctx)
        shot = self._shot(ctx, shot_ref)
        old = {
            'shot_code': shot.shot_code,
            'description': shot.description,
            'status': shot.status,
            'category': shot.category,
            'assignee_user_id': shot.assignee_user_id,
            'assignee_ids': get_horizon_shot_assignee_ids(shot),
            'assignees': serialize_horizon_shot_assignees(shot),
        }
        updated = _update_horizon_shot_no_commit(
            self.db,
            ctx.project_id,
            shot.id,
            shot_code=shot_code,
            description=description,
            status=status,
            category=category,
            assignee_user_id=assignee_user_id,
            assignee_user_ids=assignee_user_ids,
            fields_set=fields,
        )
        result = ShotCommandResult(shots=[updated])
        self._emit_update_events(result, ctx, updated, old, fields, requested_status=status, requested_category=category)
        if 'status' in fields and status is not None and status != old['status']:
            result.stats_dirty_tracker_ids.add(ctx.tracker_id)
            result.activity_records.append({'type': 'status_change', 'entity_type': 'shot', 'entity_id': updated.id, 'entity_name': updated.shot_code, 'tracker_name': ctx.tracker_name, 'old_status': old['status'], 'new_status': status})
        return result

    def append_version(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, *, file_path: str | None = None, label: str | None = None, media_asset_id: str | None = None, notes: str | None = None, created_by: str | None = None) -> ShotCommandResult:
        self._require_update_shot(ctx)
        require_horizon_project_writable(self.db, ctx.project_id)
        self._lock_history(ctx)
        shot = self._shot(ctx, shot_ref)
        normalized_file_path = self._validate_media_path(ctx, file_path) if file_path else None
        versions = list_horizon_shot_versions(self.db, ctx.project_id, shot.id)
        next_label = str(label).strip() if label is not None else next_version_label(versions)
        if not next_label:
            next_label = next_version_label(versions)
        asset = register_media_asset(self.db, ctx.project_id, normalized_file_path, storage_scope='tracker_version', commit=False) if normalized_file_path else None
        resolved_media_asset_id = asset.id if asset else self._media_asset_id(ctx, media_asset_id)
        version = _create_horizon_shot_version_no_commit(
            self.db,
            project_id=ctx.project_id,
            shot_id=shot.id,
            label=next_label,
            media_asset_id=resolved_media_asset_id,
            notes=notes,
            created_by=created_by,
        )
        result = ShotCommandResult(shots=[shot], versions=[version], stats_dirty_tracker_ids={ctx.tracker_id})
        previous_status = self._move_published_version_to_review(result, ctx, shot, version)
        if normalized_file_path:
            result.queued_media_paths.append(normalized_file_path)
        payload = {'shot_id': shot.id, 'shot_code': shot.shot_code, 'version_label': version.label}
        if previous_status is not None:
            payload.update({
                'shot_status_changed': True,
                'old_status': previous_status,
                'new_status': shot.status,
            })
        if normalized_file_path:
            payload['file_path'] = normalized_file_path
        self._emit(result, ctx, 'version_added', shot=shot, version=version, payload=payload)
        return result

    def sync_versions(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, desired_versions: list[dict], *, created_by: str | None = None) -> ShotCommandResult:
        self._require_update_shot(ctx)
        require_horizon_project_writable(self.db, ctx.project_id)
        self._lock_history(ctx)
        shot = self._shot(ctx, shot_ref)
        shot = self.db.query(HorizonShot).filter(HorizonShot.id == shot.id).with_for_update().one()
        tracker = (
            self.db.query(HorizonTracker)
            .filter(HorizonTracker.id == shot.tracker_id)
            .filter(HorizonTracker.project_id == ctx.project_id)
            .first()
        )
        if tracker is None:
            raise HTTPException(status_code=404, detail='Horizons tracker not found')
        existing_versions = list_horizon_shot_versions(self.db, ctx.project_id, shot.id)
        before_versions = [
            (version.id, version.label, version.media_asset_id, version.notes, version.share_state, version.published_at)
            for version in existing_versions
        ]
        before_latest = (shot.latest_version_label, shot.latest_media_asset_id, shot.status)
        if len(desired_versions) < len(existing_versions) and not ctx.can_delete_versions:
            raise HTTPException(status_code=403, detail='Owner access required to delete versions')
        is_deleting_versions = len(desired_versions) < len(existing_versions)
        existing_by_id = {version.id: version for version in existing_versions}

        def payload_version_id(payload: dict) -> str:
            return str(
                payload.get('id')
                or payload.get('version_id')
                or payload.get('horizons_shot_version_id')
                or ''
            ).strip()

        requested_version_ids = [payload_version_id(payload) for payload in desired_versions]
        uses_explicit_identity = any(requested_version_ids)
        claimed_existing_ids: set[str] = set()
        matched_existing_versions: list[HorizonShotVersion | None] = []
        for index, version_id in enumerate(requested_version_ids):
            version = None
            if version_id:
                version = existing_by_id.get(version_id)
                if version is None:
                    raise HTTPException(status_code=400, detail='Version does not belong to this shot')
                if version.id in claimed_existing_ids:
                    raise HTTPException(status_code=400, detail='Duplicate version id')
            elif not uses_explicit_identity and index < len(existing_versions):
                version = existing_versions[index]
            if version is not None:
                claimed_existing_ids.add(version.id)
            matched_existing_versions.append(version)
        normalized_labels: list[str] = []
        seen_labels: set[str] = set()
        for index, (payload, version) in enumerate(zip(desired_versions, matched_existing_versions)):
            label = str(payload.get('label') or payload.get('version') or index + 1).strip() or str(index + 1)
            if label in seen_labels:
                raise HTTPException(status_code=400, detail=f'Duplicate version label: {label}')
            seen_labels.add(label)
            is_delete_renumber = is_deleting_versions and label == str(index + 1)
            if version is not None and version_is_published(version) and label != version.label and not is_delete_renumber:
                raise HTTPException(
                    status_code=409,
                    detail='Published version labels cannot be changed',
                )
            normalized_labels.append(label)
        stale = [version for version in existing_versions if version.id not in claimed_existing_ids]
        if stale:
            self._delete_comments_for_versions([version.id for version in stale])
            for version in stale:
                self.db.delete(version)
            # Release unique shot/label slots before a surviving version inherits
            # a deleted version's display number.
            self.db.flush()

        now = time.time()
        synced_versions: list[HorizonShotVersion] = []
        created_versions: list[HorizonShotVersion] = []
        queued_paths: list[str] = []
        for index, (payload, version, label) in enumerate(zip(desired_versions, matched_existing_versions, normalized_labels)):
            file_path = str(payload.get('file_path') or '').strip()
            normalized_path = self._validate_media_path(ctx, file_path) if file_path else None
            media_asset_id = payload.get('media_asset_id')
            asset = register_media_asset(self.db, ctx.project_id, normalized_path, storage_scope='tracker_version', commit=False) if normalized_path else None
            if asset:
                media_asset_id = asset.id
                queued_paths.append(normalized_path)
            else:
                media_asset_id = self._media_asset_id(ctx, media_asset_id)
            if version is not None:
                version.label = label
                if (
                    version_is_published(version)
                    and (
                        (normalized_path and media_asset_id != version.media_asset_id)
                        or (media_asset_id is not None and media_asset_id != version.media_asset_id)
                    )
                ):
                    raise HTTPException(
                        status_code=409,
                        detail='Published version media cannot be replaced; add a new version instead',
                    )
                if media_asset_id is not None:
                    version.media_asset_id = media_asset_id
                elif normalized_path:
                    version.media_asset_id = None
                if 'notes' in payload:
                    version.notes = payload.get('notes')
                version.updated_at = now
            else:
                # Preserve the caller's version order even when a bulk sync
                # creates several rows inside the same clock tick.
                version_created_at = now + (index * 0.000001)
                share_state, published_at = initial_version_publication(tracker, now=version_created_at)
                if share_state == 'published' and not version_media_is_publishable(
                    self.db,
                    ctx.project_id,
                    media_asset_id,
                ):
                    share_state, published_at = 'internal', None
                version = HorizonShotVersion(
                    id=str(uuid.uuid4()),
                    project_id=ctx.project_id,
                    tracker_id=shot.tracker_id,
                    shot_id=shot.id,
                    label=label,
                    media_asset_id=media_asset_id,
                    notes=payload.get('notes'),
                    share_state=share_state,
                    published_at=published_at,
                    created_by=created_by,
                    created_at=version_created_at,
                    updated_at=now,
                )
                created_versions.append(version)
            self.db.add(version)
            synced_versions.append(version)
        if desired_versions:
            latest = synced_versions[-1]
            shot.latest_version_label = latest.label
            shot.latest_media_asset_id = latest.media_asset_id
        else:
            shot.latest_version_label = None
            shot.latest_media_asset_id = None
        self._touch(ctx, shot)
        self.db.flush()
        for version in created_versions:
            if version_is_published(version):
                set_version_share_state(self.db, version, 'published', now=version.created_at)
        result = ShotCommandResult(shots=[shot], versions=synced_versions, stats_dirty_tracker_ids={ctx.tracker_id}, queued_media_paths=list(dict.fromkeys(queued_paths)))
        if synced_versions and synced_versions[-1] in created_versions:
            self._move_published_version_to_review(result, ctx, shot, synced_versions[-1])
        after_versions = [
            (version.id, version.label, version.media_asset_id, version.notes, version.share_state, version.published_at)
            for version in synced_versions
        ]
        if before_versions != after_versions or before_latest != (shot.latest_version_label, shot.latest_media_asset_id, shot.status):
            self._emit(result, ctx, 'versions_updated', shot=shot, payload={
                'shot_id': shot.id,
                'shot_code': shot.shot_code,
                'old_count': len(before_versions),
                'count': len(after_versions),
            })
        return result

    def update_version(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, version_id: str, *, media_asset_id: str | None = None, notes: str | None = None, fields_set: set[str] | None = None) -> ShotCommandResult:
        self._require_update_shot(ctx)
        self._lock_history(ctx)
        shot = self._shot(ctx, shot_ref)
        if 'media_asset_id' in set(fields_set or set()) and media_asset_id:
            media_asset_id = self._media_asset_id(ctx, media_asset_id)
        current = next((item for item in list_horizon_shot_versions(self.db, ctx.project_id, shot.id) if item.id == version_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail='Horizons version not found')
        before = (current.media_asset_id, current.notes)
        version = _update_horizon_shot_version_no_commit(self.db, ctx.project_id, shot.id, version_id, media_asset_id=media_asset_id, notes=notes, fields_set=fields_set or set())
        result = ShotCommandResult(shots=[shot], versions=[version], stats_dirty_tracker_ids={ctx.tracker_id})
        if before != (version.media_asset_id, version.notes):
            self._emit(result, ctx, 'versions_updated', shot=shot, version=version, payload={
                'shot_id': shot.id,
                'shot_code': shot.shot_code,
                'version_label': version.label,
                'fields': sorted(fields_set or set()),
            })
        return result

    def archive_shot(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, *, reason: str | None = None) -> ShotCommandResult:
        return self._set_archived(ctx, shot_ref, archived=True, reason=reason)

    def restore_shot(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot) -> ShotCommandResult:
        return self._set_archived(ctx, shot_ref, archived=False, reason=None)

    def bulk_set_archived(
        self,
        ctx: ShotCommandContext,
        shot_refs: list[str],
        *,
        archived: bool,
        reason: str | None = None,
    ) -> ShotCommandResult:
        if not ctx.can_archive_shot or ctx.restricted_artist:
            raise HTTPException(status_code=403, detail='Artists cannot archive tracker shots')
        self._lock_history(ctx)
        resolved = self._resolve_unique_shots(ctx, normalize_bulk_shot_refs(shot_refs))
        shot_ids = sorted(shot.id for shot in resolved)
        shots = (
            self.db.query(HorizonShot)
            .filter(HorizonShot.project_id == ctx.project_id)
            .filter(HorizonShot.tracker_id == ctx.tracker_id)
            .filter(HorizonShot.id.in_(shot_ids))
            .order_by(HorizonShot.id.asc())
            .populate_existing()
            .with_for_update()
            .all()
        )
        if len(shots) != len(shot_ids):
            raise HTTPException(status_code=409, detail='The tracker changed while updating these shots. Please try again.')

        now = time.time()
        changed: list[HorizonShot] = []
        event_shots: list[dict] = []
        for shot in shots:
            if bool(shot.archived_at) == archived:
                continue
            old_state = {
                'archived_at': shot.archived_at,
                'archived_by': shot.archived_by,
                'archive_reason': shot.archive_reason,
            }
            if archived:
                shot.archived_at = now
                shot.archived_by = ctx.actor.actor_id or ctx.actor.actor_name
                shot.archive_reason = (reason or '').strip() or None
            else:
                shot.archived_at = None
                shot.archived_by = None
                shot.archive_reason = None
            shot.updated_at = now
            self.db.add(shot)
            new_state = {
                'archived_at': shot.archived_at,
                'archived_by': shot.archived_by,
                'archive_reason': shot.archive_reason,
            }
            changed.append(shot)
            event_shots.append({
                'shot_id': shot.id,
                'shot_code': shot.shot_code,
                'changes': {'archived': {'old_state': old_state, 'new_state': new_state}},
            })

        result = ShotCommandResult(
            shots=changed,
            response_hint={
                'updated': len(changed),
                'unchanged': len(shots) - len(changed),
                'status': 'archived' if archived else 'active',
            },
        )
        if not changed:
            return result
        self._touch(ctx)
        result.stats_dirty_tracker_ids.add(ctx.tracker_id)
        self._emit(result, ctx, 'shots_bulk_updated', payload={
            'count': len(changed),
            'fields': ['archived'],
            'archive_action': 'archived' if archived else 'restored',
            'shots': event_shots,
        })
        return result

    def delete_shot(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot) -> ShotCommandResult:
        if not ctx.can_delete_shot:
            raise HTTPException(status_code=403, detail='Owner access required')
        self._lock_history(ctx)
        shot = self._shot(ctx, shot_ref)
        if not shot.archived_at:
            raise HTTPException(status_code=409, detail='Move the shot to Archived before deleting it permanently')
        deleted = self._delete_shot_records(ctx, shot)
        self._touch(ctx)
        result = ShotCommandResult(stats_dirty_tracker_ids={ctx.tracker_id}, deleted=[deleted])
        self._emit(result, ctx, 'shot_deleted', shot_id=deleted['shot_id'], payload=deleted)
        return result

    def bulk_delete_shots(self, ctx: ShotCommandContext, shot_refs: list[str]) -> ShotCommandResult:
        if not ctx.can_delete_shot:
            raise HTTPException(status_code=403, detail='Owner access required')
        self._lock_history(ctx)
        shots = self._resolve_unique_shots(ctx, normalize_bulk_shot_refs(shot_refs))
        if any(not shot.archived_at for shot in shots):
            raise HTTPException(status_code=409, detail='Move every shot to Archived before deleting them permanently')
        result = ShotCommandResult(stats_dirty_tracker_ids={ctx.tracker_id})
        deleted = []
        for shot in shots:
            deleted.append(self._delete_shot_records(ctx, shot))
        self._touch(ctx)
        result.deleted = deleted
        self._emit(result, ctx, 'shots_deleted_bulk', payload={'count': len(deleted), 'shots': deleted, 'source_files_deleted': False})
        result.response_hint = {'deleted': len(deleted), 'source_files_deleted': False}
        return result

    def bulk_update_shots(self, ctx: ShotCommandContext, shot_refs: list[str], *, fields_set: set[str], status: str | None = None, category: str | None = None, assignee_user_id: str | None = None, assignee_user_ids: list[str] | None = None, event_type: str = 'shots_bulk_updated') -> ShotCommandResult:
        self._require_update_shot(ctx)
        fields = set(fields_set or set()) & {'status', 'category', 'assignee_user_id', 'assignee_user_ids'}
        if not fields:
            raise HTTPException(status_code=400, detail='At least one bulk update field is required')
        if ctx.restricted_artist and fields - {'status', 'category'}:
            raise HTTPException(status_code=403, detail='Artists can only bulk update shot status and tag')
        self._lock_history(ctx)
        next_status = normalize_shot_status(status) if 'status' in fields else None
        next_category = category if 'category' in fields else None
        next_assignee_ids, next_assignees = self._resolve_assignees(assignee_user_id, assignee_user_ids, fields)
        now = time.time()
        changed: list[dict] = []
        unchanged: list[dict] = []
        for shot in self._resolve_unique_shots(ctx, normalize_bulk_shot_refs(shot_refs)):
            changes: dict[str, dict] = {}
            if 'status' in fields and shot.status != next_status:
                changes['status'] = {'old_value': shot.status, 'new_value': next_status}
                shot.status = next_status
            if 'category' in fields and (shot.category or None) != next_category:
                changes['category'] = {'old_value': shot.category or None, 'new_value': next_category, 'old_tag': shot.category or None, 'tag': next_category}
                shot.category = next_category
            if {'assignee_user_id', 'assignee_user_ids'} & fields:
                old_ids = get_horizon_shot_assignee_ids(shot)
                old_assignees = serialize_horizon_shot_assignees(shot)
                if old_ids != next_assignee_ids:
                    old_assignee_user_id = shot.assignee_user_id or None
                    set_horizon_shot_assignees(self.db, shot, next_assignee_ids, assigned_by=ctx.actor.actor_id)
                    changes['assignee_user_id'] = {
                        'old_value': old_assignee_user_id,
                        'new_value': shot.assignee_user_id,
                        'old_assignee_name': old_assignees[0].get('display_name') if old_assignees else None,
                        'assignee_name': next_assignees[0].get('display_name') if next_assignees else None,
                        'old_assignee_user_ids': old_ids,
                        'assignee_user_ids': next_assignee_ids,
                        'old_assignees': old_assignees,
                        'assignees': next_assignees,
                        'added_assignee_user_ids': [user_id for user_id in next_assignee_ids if user_id not in old_ids],
                        'removed_assignee_user_ids': [user_id for user_id in old_ids if user_id not in next_assignee_ids],
                    }
            if not changes:
                unchanged.append({'shot_id': shot.id, 'shot_code': shot.shot_code})
                continue
            shot.updated_at = now
            self.db.add(shot)
            changed.append({'shot_id': shot.id, 'shot_code': shot.shot_code, 'changes': changes})
        result = ShotCommandResult(response_hint={'updated': len(changed), 'unchanged': len(unchanged), 'fields': sorted(fields)}, shots=[])
        if changed:
            self._touch(ctx)
            if 'status' in fields:
                result.stats_dirty_tracker_ids.add(ctx.tracker_id)
                result.activity_records.append({'type': 'status_change', 'entity_type': 'tracker', 'entity_id': ctx.tracker_id, 'entity_name': ctx.tracker_name, 'shot_count': len(changed), 'new_status': next_status})
            payload = {'count': len(changed), 'fields': sorted(fields), 'shots': changed}
            if event_type == 'status_changed_bulk':
                payload = {'count': len(changed), 'new_value': next_status, 'new_label': next_status.replace('_', ' '), 'shots': [{'shot_id': item['shot_id'], 'shot_code': item['shot_code'], 'old_status': item['changes']['status']['old_value'], 'new_status': next_status} for item in changed]}
            self._emit(result, ctx, event_type, payload=payload)
        result.response_hint['shots'] = payload.get('shots', changed) if changed else []
        return result

    def bulk_import_shots(self, ctx: ShotCommandContext, files: list[str], *, created_by: str | None = None) -> ShotCommandResult:
        self._lock_history(ctx)
        existing_ids = {shot.shot_code for shot in self.db.query(HorizonShot).filter(HorizonShot.project_id == ctx.project_id).filter(HorizonShot.tracker_id == ctx.tracker_id).all()}
        result = ShotCommandResult(stats_dirty_tracker_ids={ctx.tracker_id})
        imported_event_shots: list[dict] = []
        nested_ctx = replace(ctx, event_mode='none')
        for file_path in sorted(files or [], key=lambda path: [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r'(\d+)', Path(path).stem)]):
            shot_code = Path(file_path).stem
            base_code = shot_code
            counter = 1
            while shot_code in existing_ids:
                shot_code = f'{base_code}_{counter}'
                counter += 1
            existing_ids.add(shot_code)
            created = self.create_shot(nested_ctx, shot_code=shot_code, description='', status='not_started')
            result.extend(created)
            versioned = self.append_version(nested_ctx, created.shots[0], file_path=file_path, label='1', created_by=created_by)
            result.extend(versioned)
            imported_event_shots.append({'id': created.shots[0].id, 'shot_code': created.shots[0].shot_code})
        deduped_shots: list[HorizonShot] = []
        seen_shot_ids: set[str] = set()
        for shot in result.shots:
            if shot.id in seen_shot_ids:
                continue
            seen_shot_ids.add(shot.id)
            deduped_shots.append(shot)
        result.shots = deduped_shots
        result.events = [event for event in result.events if event.get('event_type') not in {'shot_created', 'version_added'}]
        if imported_event_shots:
            self._emit(result, ctx, 'shots_imported', payload={'count': len(imported_event_shots), 'shots': imported_event_shots})
        result.response_hint = {'imported': len(imported_event_shots)}
        return result

    def bulk_update_versions_from_folder(self, ctx: ShotCommandContext, folder_path: str, shots: list[HorizonShot], *, created_by: str | None = None) -> ShotCommandResult:
        self._require_update_shot(ctx)
        self._lock_history(ctx)
        folder = (folder_path or '').strip().strip('/')
        if not folder:
            raise HTTPException(status_code=400, detail='folder_path is required')
        self._enforce_restricted_artist_media_path(ctx, folder, storage_scope='tracker_version')
        folder_fs, _job_key, _scope = resolve_media_target(folder, ctx.project_id, storage_scope='tracker_version')
        if not folder_fs or not folder_fs.exists() or not folder_fs.is_dir():
            raise HTTPException(status_code=404, detail='Folder not found')
        stem_to_relpath: dict[str, str] = {}
        stem_to_mtime: dict[str, float] = {}
        for entry in folder_fs.iterdir():
            try:
                if not entry.is_file() or entry.name.startswith('.') or (not is_video(entry) and not is_image(entry)):
                    continue
                stem = entry.stem.strip().lower()
                mtime = entry.stat().st_mtime
                if stem and (stem not in stem_to_mtime or mtime > stem_to_mtime[stem]):
                    stem_to_mtime[stem] = mtime
                    stem_to_relpath[stem] = f'{folder}/{entry.name}' if folder else entry.name
            except Exception:
                continue
        if not stem_to_relpath:
            return ShotCommandResult(response_hint={'scanned': 0, 'matched_files': 0, 'updated_versions': 0, 'skipped_existing': 0, 'unmatched_files': []})
        shots_by_stem: dict[str, list[HorizonShot]] = {}
        version_cache: dict[str, list[HorizonShotVersion]] = {}
        asset_map: dict[str, MediaAsset] = {}
        validated_shots = [self._shot(ctx, shot) for shot in shots]
        for shot in validated_shots:
            versions = list_horizon_shot_versions(self.db, ctx.project_id, shot.id)
            version_cache[shot.id] = versions
            shots_by_stem.setdefault((shot.shot_code or '').strip().lower(), []).append(shot)
            for version in versions:
                if version.media_asset_id and version.media_asset_id not in asset_map:
                    asset = self.db.query(MediaAsset).filter(MediaAsset.id == version.media_asset_id).first()
                    if asset:
                        asset_map[asset.id] = asset
            latest_asset = asset_map.get(versions[-1].media_asset_id) if versions and versions[-1].media_asset_id else None
            latest_stem = Path(latest_asset.file_path).stem.strip().lower() if latest_asset and latest_asset.file_path else ''
            if latest_stem:
                shots_by_stem.setdefault(latest_stem, []).append(shot)
        result = ShotCommandResult()
        nested_ctx = replace(ctx, event_mode='none')
        unmatched_files: list[str] = []
        matched_files = updated_versions = skipped_existing = 0
        touched_shots: dict[str, dict] = {}
        for stem, new_file_path in stem_to_relpath.items():
            targets = shots_by_stem.get(stem) or []
            if not targets:
                unmatched_files.append(new_file_path)
                continue
            matched_files += 1
            seen_file_shot_ids: set[str] = set()
            for shot in targets:
                if shot.id in seen_file_shot_ids:
                    continue
                seen_file_shot_ids.add(shot.id)
                versions = version_cache.get(shot.id) or []
                existing_paths = {asset_map[version.media_asset_id].file_path for version in versions if version.media_asset_id in asset_map and asset_map[version.media_asset_id].file_path}
                latest_path = None
                if versions and versions[-1].media_asset_id in asset_map:
                    latest_path = asset_map[versions[-1].media_asset_id].file_path
                if latest_path == new_file_path or new_file_path in existing_paths:
                    skipped_existing += 1
                    continue
                appended = self.append_version(nested_ctx, shot, file_path=new_file_path, created_by=created_by)
                result.extend(appended)
                version_cache.setdefault(shot.id, []).append(appended.versions[0])
                if appended.versions[0].media_asset_id and appended.versions[0].media_asset_id not in asset_map:
                    asset = self.db.query(MediaAsset).filter(MediaAsset.id == appended.versions[0].media_asset_id).first()
                    if asset:
                        asset_map[asset.id] = asset
                updated_versions += 1
                touched_shots[shot.id] = {
                    'id': shot.id,
                    'shot_code': shot.shot_code,
                    'version_id': appended.versions[0].id,
                }
        if updated_versions:
            result.stats_dirty_tracker_ids.add(ctx.tracker_id)
            self._emit(result, ctx, 'versions_bulk_updated', payload={'count': updated_versions, 'shots': list(touched_shots.values()), 'folder_path': folder})
        result.response_hint = {'scanned': len(stem_to_relpath), 'matched_files': matched_files, 'updated_versions': updated_versions, 'skipped_existing': skipped_existing, 'unmatched_files': unmatched_files[:200], 'unmatched_count': len(unmatched_files)}
        return result

    def reorder_shots(self, ctx: ShotCommandContext, shot_order: list[str]) -> ShotCommandResult:
        self._require_update_shot(ctx)
        if ctx.restricted_artist:
            raise HTTPException(status_code=403, detail='Artists cannot reorder tracker shots')
        self._lock_history(ctx)
        shots = self.db.query(HorizonShot).filter(HorizonShot.project_id == ctx.project_id).filter(HorizonShot.tracker_id == ctx.tracker_id).filter(HorizonShot.archived_at.is_(None)).order_by(HorizonShot.created_at.asc(), HorizonShot.id.asc()).all()
        if not shots:
            return ShotCommandResult(response_hint={'status': 'reordered'})
        lookup = {}
        for shot in shots:
            lookup.setdefault(shot.id, shot)
            lookup.setdefault(shot.shot_code, shot)
        ordered: list[HorizonShot] = []
        seen_ids: set[str] = set()
        for ref in shot_order or []:
            shot = lookup.get(ref)
            if shot and shot.id not in seen_ids:
                ordered.append(shot)
                seen_ids.add(shot.id)
        ordered.extend(shot for shot in shots if shot.id not in seen_ids)
        base_times = sorted((shot.created_at for shot in shots), key=lambda value: value or 0)
        now = time.time()
        for index, shot in enumerate(ordered):
            shot.created_at = base_times[index] if index < len(base_times) else now + (index * 0.001)
            shot.updated_at = now
            self.db.add(shot)
        self._touch(ctx)
        result = ShotCommandResult(shots=ordered, response_hint={'status': 'reordered'})
        self._emit(result, ctx, 'shot_reordered', payload={'count': len(ordered), 'shots': [{'id': item.id, 'shot_code': item.shot_code} for item in ordered]})
        return result

    def create_or_append_from_media(self, ctx: ShotCommandContext, *, source_path: str, shot_ref: str | None, shot_code: str | None, create_shot_if_missing: bool, description: str | None = None, status: str | None = None, category: str | None = None, version_label: str | None = None, notes: str | None = None, created_by: str | None = None) -> ShotCommandResult:
        self._require_update_shot(ctx)
        self._lock_history(ctx)
        normalized_source_path = str(source_path or '').strip().strip('/')
        if not normalized_source_path:
            raise HTTPException(status_code=400, detail='source_path is required')
        source_file = get_safe_path(normalized_source_path)
        if not source_file.exists() or not source_file.is_file():
            raise HTTPException(status_code=400, detail='Storage file not found')
        self._enforce_restricted_artist_media_path(ctx, normalized_source_path, storage_scope='media_root')
        shot = self._maybe_shot(ctx, shot_ref) if shot_ref else None
        if shot is None and shot_code:
            shot = self._maybe_shot(ctx, shot_code)
        created_shot = False
        result = ShotCommandResult()
        if shot is None:
            if not shot_code or not create_shot_if_missing:
                raise HTTPException(status_code=404, detail='Horizons shot not found')
            created = self.create_shot(ctx, shot_code=shot_code, description=description, status=status, category=category)
            result.extend(created)
            shot = created.shots[0]
            created_shot = True
        else:
            if shot_code and shot.shot_code != shot_code:
                raise HTTPException(status_code=409, detail='shot_ref and shot_code refer to different shots')
        asset = register_media_asset(self.db, ctx.project_id, normalized_source_path, storage_scope='media_root', commit=False)
        if asset is None:
            raise HTTPException(status_code=400, detail='Failed to register media from the selected storage path')
        existing_versions = list_horizon_shot_versions(self.db, ctx.project_id, shot.id)
        normalized_label = str(version_label or '').strip() or next_version_label(existing_versions)
        normalized_notes = str(notes or '').strip() or None
        existing = next((version for version in existing_versions if version.label == normalized_label), None)
        created_version = False
        if existing is not None:
            if existing.media_asset_id != asset.id or (existing.notes or None) != normalized_notes:
                raise HTTPException(status_code=409, detail='Version label already exists on shot with different media')
            version = existing
        else:
            version = _create_horizon_shot_version_no_commit(
                self.db,
                project_id=ctx.project_id,
                shot_id=shot.id,
                label=normalized_label,
                media_asset_id=asset.id,
                notes=normalized_notes,
                created_by=created_by,
            )
            result.versions.append(version)
            result.stats_dirty_tracker_ids.add(ctx.tracker_id)
            previous_status = self._move_published_version_to_review(result, ctx, shot, version)
            payload = {'shot_id': shot.id, 'shot_code': shot.shot_code, 'version_label': version.label, 'file_path': asset.file_path}
            if previous_status is not None:
                payload.update({
                    'shot_status_changed': True,
                    'old_status': previous_status,
                    'new_status': shot.status,
                })
            self._emit(result, ctx, 'version_added', shot=shot, version=version, payload=payload)
            created_version = True
        result.response_hint.update({
            'created_shot': created_shot,
            'created_version': created_version,
            'version': version,
            'asset': asset,
        })
        return result

    def _set_archived(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot, *, archived: bool, reason: str | None) -> ShotCommandResult:
        if not ctx.can_archive_shot or ctx.restricted_artist:
            raise HTTPException(status_code=403, detail='Artists cannot archive tracker shots')
        self._lock_history(ctx)
        resolved = self._shot(ctx, shot_ref)
        shot = (
            self.db.query(HorizonShot)
            .filter(HorizonShot.project_id == ctx.project_id)
            .filter(HorizonShot.tracker_id == ctx.tracker_id)
            .filter(HorizonShot.id == resolved.id)
            .populate_existing()
            .with_for_update()
            .one()
        )
        if archived and shot.archived_at:
            return ShotCommandResult(shots=[shot], response_hint={'status': 'archived'})
        if not archived and not shot.archived_at:
            return ShotCommandResult(shots=[shot], response_hint={'status': 'active'})
        now = time.time()
        previous_archive_state = {
            'archived_at': shot.archived_at,
            'archived_by': shot.archived_by,
            'archive_reason': shot.archive_reason,
        }
        if archived:
            shot.archived_at = now
            shot.archived_by = ctx.actor.actor_id or ctx.actor.actor_name
            shot.archive_reason = (reason or '').strip() or None
            event_type = 'shot_archived'
            status = 'archived'
        else:
            shot.archived_at = None
            shot.archived_by = None
            shot.archive_reason = None
            event_type = 'shot_restored'
            status = 'active'
        self._touch(ctx, shot)
        result = ShotCommandResult(shots=[shot], stats_dirty_tracker_ids={ctx.tracker_id}, response_hint={'status': status})
        next_archive_state = {
            'archived_at': shot.archived_at,
            'archived_by': shot.archived_by,
            'archive_reason': shot.archive_reason,
        }
        self._emit(result, ctx, event_type, shot=shot, payload={
            'shot_id': shot.id,
            'shot_code': shot.shot_code,
            'archived_at': shot.archived_at,
            'previous_archived_at': previous_archive_state['archived_at'],
            'old_state': previous_archive_state,
            'new_state': next_archive_state,
        })
        return result
