from __future__ import annotations

import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Comment, HorizonProject, HorizonShot, HorizonShotAssignee, HorizonShotVersion, HorizonTracker, MediaAsset
from app.services.comments import preserve_comment_attachments
from app.services.horizons.media import can_access_horizon_media_asset_id
from app.services.horizons.projects import get_horizon_project
from app.services.horizons.shots import get_horizon_shot_by_ref
from app.services.horizons.team import (
    get_horizon_assignable_user,
    get_horizon_shot_assignee_ids,
    get_horizon_user_workspace_path,
    serialize_horizon_shot_assignees,
    serialize_horizon_team_user,
)
from app.services.horizons.trackers import get_horizon_tracker_by_ref
from app.services.media import is_image, is_video
from app.services.media_resolution import resolve_media_target
from app.services.shot_command_types import ShotCommandContext, ShotCommandResult
from app.services.tracker_events import create_tracker_event


class ShotCommandBase:
    def __init__(self, db: Session):
        self.db = db

    def _lock_history(self, ctx: ShotCommandContext) -> HorizonTracker:
        from app.services.tracker_history import prepare_tracker_history_mutation

        return prepare_tracker_history_mutation(
            self.db,
            project_id=ctx.project_id,
            tracker_id=ctx.tracker_id,
        )

    def _emit_update_events(self, result: ShotCommandResult, ctx: ShotCommandContext, shot: HorizonShot, old: dict, fields: set[str], *, requested_status: str | None, requested_category: str | None) -> None:
        if 'shot_code' in fields and shot.shot_code != old['shot_code']:
            self._emit(result, ctx, 'shot_renamed', shot=shot, payload={'shot_id': shot.id, 'shot_code': shot.shot_code, 'old_value': old['shot_code'], 'new_value': shot.shot_code})
        if 'description' in fields and (shot.description or '') != (old['description'] or ''):
            self._emit(result, ctx, 'brief_changed', shot=shot, payload={'shot_id': shot.id, 'shot_code': shot.shot_code, 'old_value': old['description'] or '', 'new_value': shot.description or ''})
        if 'status' in fields and requested_status is not None and requested_status != old['status']:
            self._emit(result, ctx, 'status_changed', shot=shot, payload={'shot_id': shot.id, 'shot_code': shot.shot_code, 'old_value': old['status'], 'new_value': shot.status, 'old_label': old['status'].replace('_', ' '), 'new_label': shot.status.replace('_', ' ')})
        if 'category' in fields and requested_category != old['category']:
            self._emit(result, ctx, 'category_changed', shot=shot, payload={'shot_id': shot.id, 'shot_code': shot.shot_code, 'old_value': old['category'], 'new_value': shot.category, 'old_tag': old['category'], 'tag': shot.category})
        if {'assignee_user_id', 'assignee_user_ids'} & fields and get_horizon_shot_assignee_ids(shot) != old['assignee_ids']:
            new_ids = get_horizon_shot_assignee_ids(shot)
            new_assignees = serialize_horizon_shot_assignees(shot)
            self._emit(result, ctx, 'assignee_changed', shot=shot, payload={
                'shot_id': shot.id,
                'shot_code': shot.shot_code,
                'old_value': old['assignee_user_id'],
                'new_value': shot.assignee_user_id,
                'old_assignee_name': old['assignees'][0].get('display_name') if old['assignees'] else None,
                'assignee_name': new_assignees[0].get('display_name') if new_assignees else None,
                'old_assignee_user_ids': old['assignee_ids'],
                'assignee_user_ids': new_ids,
                'old_assignees': old['assignees'],
                'assignees': new_assignees,
                'added_assignee_user_ids': [user_id for user_id in new_ids if user_id not in old['assignee_ids']],
                'removed_assignee_user_ids': [user_id for user_id in old['assignee_ids'] if user_id not in new_ids],
            })

    def _emit(self, result: ShotCommandResult, ctx: ShotCommandContext, event_type: str, *, shot: HorizonShot | None = None, version: HorizonShotVersion | None = None, shot_id: str | None = None, payload: dict | None = None) -> None:
        event = {'event_type': event_type, 'shot_id': shot.id if shot is not None else shot_id, 'shot_version_id': version.id if version is not None else None, 'payload': payload or {}}
        result.events.append(event)
        if ctx.event_mode == 'none':
            return
        create_tracker_event(
            self.db,
            project_id=ctx.project_id,
            tracker_id=ctx.tracker_id,
            shot_id=event['shot_id'],
            shot_version_id=event['shot_version_id'],
            event_type=event_type,
            actor_id=ctx.actor.actor_id,
            actor_name=ctx.actor.actor_name,
            source=ctx.actor.source,
            payload=event['payload'],
        )

    def _touch(self, ctx: ShotCommandContext, shot: HorizonShot | None = None) -> None:
        now = time.time()
        tracker = self._tracker(ctx)
        project = self._project(ctx)
        if shot is not None:
            shot.updated_at = now
            self.db.add(shot)
        tracker.updated_at = now
        project.updated_at = now
        self.db.add(tracker)
        self.db.add(project)
        self.db.flush()

    def _shot(self, ctx: ShotCommandContext, shot_ref: str | HorizonShot) -> HorizonShot:
        if isinstance(shot_ref, HorizonShot):
            if shot_ref.project_id != ctx.project_id or shot_ref.tracker_id != ctx.tracker_id:
                raise HTTPException(status_code=404, detail='Shot not found')
            return shot_ref
        return get_horizon_shot_by_ref(self.db, ctx.project_id, shot_ref, tracker_id=ctx.tracker_id)

    def _media_asset(self, ctx: ShotCommandContext, media_asset_id: str | None) -> MediaAsset | None:
        normalized_asset_id = str(media_asset_id or '').strip()
        if not normalized_asset_id:
            return None
        asset = (
            self.db.query(MediaAsset)
            .filter(MediaAsset.id == normalized_asset_id)
            .filter(MediaAsset.project_id == ctx.project_id)
            .first()
        )
        if asset is None:
            raise HTTPException(status_code=400, detail='Media asset not found for project')
        if ctx.restricted_artist and not can_access_horizon_media_asset_id(
            self.db,
            ctx.project_id,
            asset.id,
            user=ctx.actor.user,
            access_role=ctx.access_role,
        ):
            raise HTTPException(status_code=403, detail='Artists can only use files inside their workspace')
        return asset

    def _media_asset_id(self, ctx: ShotCommandContext, media_asset_id: str | None) -> str | None:
        asset = self._media_asset(ctx, media_asset_id)
        return asset.id if asset is not None else None

    def _maybe_shot(self, ctx: ShotCommandContext, shot_ref: str | None) -> HorizonShot | None:
        try:
            return self._shot(ctx, shot_ref or '')
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise

    def _tracker(self, ctx: ShotCommandContext) -> HorizonTracker:
        return get_horizon_tracker_by_ref(self.db, ctx.project_id, ctx.tracker_id)

    def _project(self, ctx: ShotCommandContext) -> HorizonProject:
        return get_horizon_project(self.db, ctx.project_id)

    def _resolve_unique_shots(self, ctx: ShotCommandContext, shot_refs: list[str]) -> list[HorizonShot]:
        shots: list[HorizonShot] = []
        seen_ids: set[str] = set()
        for shot_ref in shot_refs:
            shot = self._shot(ctx, shot_ref)
            if shot.id not in seen_ids:
                shots.append(shot)
                seen_ids.add(shot.id)
        return shots

    def _validate_media_path(self, ctx: ShotCommandContext, file_path: str | None) -> str:
        normalized = (file_path or '').strip().strip('/')
        if not normalized:
            raise HTTPException(status_code=400, detail='Tracker media file is required')
        self._enforce_restricted_artist_media_path(ctx, normalized, storage_scope='tracker_version')
        full_path, _job_key, _scope = resolve_media_target(normalized, ctx.project_id, storage_scope='tracker_version')
        if not full_path or not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail='Tracker media file not found')
        if not is_video(full_path) and not is_image(full_path):
            raise HTTPException(status_code=400, detail='Tracker media must be an image or video file')
        return normalized

    def _enforce_restricted_artist_media_path(self, ctx: ShotCommandContext, normalized_path: str, *, storage_scope: str | None = None) -> None:
        if not ctx.restricted_artist:
            return
        normalized = (normalized_path or '').strip().strip('/')
        if not normalized:
            raise HTTPException(status_code=403, detail='Artists can only use files inside their workspace')
        try:
            workspace_path = get_horizon_user_workspace_path(ctx.actor.user)
        except HTTPException:
            workspace_path = ''
        if storage_scope != 'media_root' and workspace_path and (normalized == workspace_path or normalized.startswith(f'{workspace_path}/')):
            return
        asset_query = (
            self.db.query(MediaAsset)
            .filter(MediaAsset.project_id == ctx.project_id)
            .filter(MediaAsset.file_path == normalized)
            .filter(MediaAsset.unavailable_at.is_(None))
        )
        if storage_scope == 'media_root':
            asset_query = asset_query.filter(MediaAsset.storage_scope == 'media_root')
        for asset in asset_query.all():
            if can_access_horizon_media_asset_id(
                self.db,
                ctx.project_id,
                asset.id,
                user=ctx.actor.user,
                access_role=ctx.access_role,
            ):
                return
        raise HTTPException(status_code=403, detail='Artists can only use files inside their workspace')

    def _delete_comments_for_versions(self, version_ids: list[str]) -> None:
        if not version_ids:
            return
        linked_comments = self.db.query(Comment).filter(Comment.horizons_shot_version_id.in_(version_ids)).all()
        for comment in linked_comments:
            preserve_comment_attachments(comment)
            self.db.delete(comment)
        self.db.flush()

    def _delete_shot_records(self, ctx: ShotCommandContext, shot: HorizonShot) -> dict:
        deleted = {'shot_id': shot.id, 'shot_code': shot.shot_code}
        version_ids = [version_id for (version_id,) in self.db.query(HorizonShotVersion.id).filter(HorizonShotVersion.project_id == ctx.project_id).filter(HorizonShotVersion.shot_id == shot.id).all()]
        self._delete_comments_for_versions(version_ids)
        if version_ids:
            self.db.query(HorizonShotVersion).filter(HorizonShotVersion.project_id == ctx.project_id).filter(HorizonShotVersion.id.in_(version_ids)).delete(synchronize_session=False)
        self.db.query(HorizonShotAssignee).filter(
            HorizonShotAssignee.project_id == ctx.project_id,
            HorizonShotAssignee.shot_id == shot.id,
        ).delete(synchronize_session=False)
        self.db.delete(shot)
        self.db.flush()
        return deleted

    def _resolve_assignees(self, assignee_user_id: str | None, assignee_user_ids: list[str] | None, fields: set[str]) -> tuple[list[str], list[dict]]:
        if not ({'assignee_user_id', 'assignee_user_ids'} & fields):
            return [], []
        refs = assignee_user_ids if 'assignee_user_ids' in fields else ([assignee_user_id] if assignee_user_id else [])
        ids: list[str] = []
        assignees: list[dict] = []
        for ref in refs or []:
            assignee = serialize_horizon_team_user(get_horizon_assignable_user(ref))
            if not assignee:
                raise HTTPException(status_code=400, detail='Assignable team account not found')
            if assignee['id'] in ids:
                continue
            ids.append(assignee['id'])
            assignees.append(assignee)
        return ids, assignees
