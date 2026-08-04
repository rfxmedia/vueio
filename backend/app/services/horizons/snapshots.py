from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    HorizonShotVersion,
    HorizonTracker,
    MediaAsset,
)

from .projects import get_horizon_project, get_horizon_project_access_role, serialize_horizon_project
from .shots import list_visible_horizon_shots
from .team import get_horizon_shot_assignee_ids, serialize_horizon_shot_assignee, serialize_horizon_shot_assignees

def build_horizon_project_snapshot(
    db: Session,
    project_id: str,
    *,
    user: dict | None = None,
    access_role: str | None = None,
    include_trackers: bool = False,
    include_shots: bool = False,
    include_latest_files: bool = False,
    limit_trackers_per_project: int | None = None,
    limit_shots_per_tracker: int | None = None,
) -> dict:
    project = get_horizon_project(db, project_id)
    if access_role is None and user is not None:
        access_role = get_horizon_project_access_role(db, project, user)
    payload = serialize_horizon_project(db, project, user=user, access_role=access_role)

    if not include_trackers:
        return payload

    trackers = (
        db.query(HorizonTracker)
        .filter(HorizonTracker.project_id == project_id)
        .order_by(HorizonTracker.created_at.asc())
        .all()
    )
    if limit_trackers_per_project and limit_trackers_per_project > 0:
        trackers = trackers[:limit_trackers_per_project]

    tracker_payloads = []
    for tracker in trackers:
        visible_shots = list_visible_horizon_shots(db, project_id, tracker_id=tracker.id, user=user, access_role=access_role)
        tracker_entry = {
            'id': tracker.id,
            'slug': tracker.slug,
            'name': tracker.name,
            'stats': {
                'totalShots': len(visible_shots),
                'doneShots': sum(1 for shot in visible_shots if shot.status == 'done'),
            },
        }
        if include_shots:
            shots = visible_shots
            if limit_shots_per_tracker and limit_shots_per_tracker > 0:
                shots = shots[:limit_shots_per_tracker]

            shot_payloads = []
            for shot in shots:
                shot_entry = {
                    'id': shot.id,
                    'shot_id': shot.shot_code,
                    'shot_code': shot.shot_code,
                    'description': shot.description,
                    'status': shot.status,
                    'category': shot.category,
                    'tag': shot.category,
                    'assignee_user_ids': get_horizon_shot_assignee_ids(shot),
                    'assignees': serialize_horizon_shot_assignees(shot),
                    'assignee_user_id': shot.assignee_user_id,
                    'assignee': serialize_horizon_shot_assignee(shot),
                    'latest_version_label': shot.latest_version_label,
                    'latest_media_asset_id': shot.latest_media_asset_id,
                }
                if include_latest_files:
                    latest_files = []
                    latest_version_payload = None
                    if shot.latest_media_asset_id:
                        asset = db.query(MediaAsset).filter(MediaAsset.id == shot.latest_media_asset_id).first()
                        latest_version = (
                            db.query(HorizonShotVersion)
                            .filter(HorizonShotVersion.project_id == shot.project_id)
                            .filter(HorizonShotVersion.shot_id == shot.id)
                            .filter(HorizonShotVersion.media_asset_id == shot.latest_media_asset_id)
                            .order_by(HorizonShotVersion.updated_at.desc(), HorizonShotVersion.created_at.desc(), HorizonShotVersion.id.asc())
                            .first()
                        )
                        if asset:
                            latest_files.append(asset.file_path)
                            latest_version_payload = {
                                'id': latest_version.id if latest_version else None,
                                'version': shot.latest_version_label,
                                'file_path': asset.file_path,
                                'media_asset_id': asset.id,
                            }
                    shot_entry['latest_files'] = latest_files
                    shot_entry['latest_version'] = latest_version_payload
                shot_payloads.append(shot_entry)
            tracker_entry['shots'] = shot_payloads
        tracker_payloads.append(tracker_entry)

    payload['trackers'] = tracker_payloads
    return payload
