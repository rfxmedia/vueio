from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models import HorizonProject, HorizonShot, HorizonShotVersion
from app.services.horizons_fresh import can_access_horizon_shot_version_id, list_visible_horizon_shots
from app.services.horizons.version_publication import (
    VERSION_SHARE_STATE_PUBLISHED,
    version_publication_sort_key,
)
from app.services.naming import safe_name_part
from app.services.project_content_gateway import resolve_horizons_object_auth, resolve_horizons_object_share
from app.services.zip_utils import build_zip_entries, start_zip_package_job


def tracker_latest_zip_filename(project: HorizonProject, tracker_name: str, filename: str | None = None) -> str:
    requested = str(filename or '').strip()
    if requested:
        return requested if requested.lower().endswith('.zip') else f'{requested}.zip'
    project_part = safe_name_part(project.title or project.slug or project.id, 'project')
    tracker_part = safe_name_part(tracker_name, 'tracker')
    return f'{project_part}-{tracker_part}-latest-versions.zip'


def _version_sort_key(version: HorizonShotVersion) -> tuple[float, float, str]:
    raw = str(version.label or '').strip()
    direct = None
    try:
        direct = float(raw)
    except Exception:
        match = re.search(r'(\d+(?:\.\d+)?)(?!.*\d)', raw)
        if match:
            try:
                direct = float(match.group(1))
            except Exception:
                direct = None
    return (
        direct if direct is not None else -1,
        float(version.created_at or 0),
        str(version.id or ''),
    )


def _latest_versions_by_shot(
    db: Session,
    project_id: str,
    tracker_id: str,
    shots: Iterable[HorizonShot],
    *,
    published_only: bool = False,
) -> dict[str, HorizonShotVersion]:
    shot_ids = [shot.id for shot in shots if shot.id]
    if not shot_ids:
        return {}

    query = (
        db.query(HorizonShotVersion)
        .filter(HorizonShotVersion.project_id == project_id)
        .filter(HorizonShotVersion.tracker_id == tracker_id)
        .filter(HorizonShotVersion.shot_id.in_(shot_ids))
    )
    if published_only:
        query = query.filter(HorizonShotVersion.share_state == VERSION_SHARE_STATE_PUBLISHED)
    versions = query.all()
    grouped: dict[str, list[HorizonShotVersion]] = {}
    for version in versions:
        grouped.setdefault(version.shot_id, []).append(version)
    return {
        shot_id: sorted(
            items,
            key=version_publication_sort_key if published_only else _version_sort_key,
        )[-1]
        for shot_id, items in grouped.items()
        if items
    }


def _filter_shots_by_refs(shots: list[HorizonShot], shot_refs: list[str] | None) -> list[HorizonShot]:
    refs = {str(ref or '').strip() for ref in (shot_refs or []) if str(ref or '').strip()}
    if not refs:
        return shots
    return [shot for shot in shots if str(shot.id or '') in refs or str(shot.shot_code or '') in refs]


def tracker_latest_entry_arcname(shot: HorizonShot, full_path: Path) -> str:
    shot_part = safe_name_part(getattr(shot, 'shot_code', None) or getattr(shot, 'id', None), 'shot')
    file_part = safe_name_part(full_path.name, 'version')
    return f'{shot_part} - {file_part}'


def collect_tracker_latest_version_entries(
    db: Session,
    *,
    project: HorizonProject,
    tracker_id: str,
    user: dict | None = None,
    access_role: str | None = None,
    shot_refs: list[str] | None = None,
    share=None,
) -> tuple[list[tuple[Path, str]], int, int, list[str]]:
    visible_shots = list_visible_horizon_shots(db, project.id, tracker_id=tracker_id, user=user, access_role=access_role)
    target_shots = _filter_shots_by_refs(visible_shots, shot_refs)
    if shot_refs and not target_shots:
        raise HTTPException(status_code=404, detail='No visible selected shots found')

    latest_by_shot = _latest_versions_by_shot(
        db,
        project.id,
        tracker_id,
        target_shots,
        published_only=share is not None,
    )
    entries: list[tuple[Path, str]] = []
    included_version_ids: list[str] = []
    missing_count = 0

    for shot in target_shots:
        latest = latest_by_shot.get(shot.id)
        if not latest or not latest.media_asset_id:
            missing_count += 1
            continue
        if not can_access_horizon_shot_version_id(db, project.id, latest.id, user=user, access_role=access_role):
            missing_count += 1
            continue
        try:
            resolved = (
                resolve_horizons_object_share(share, db, version_id=latest.id)
                if share is not None
                else resolve_horizons_object_auth(db, project.id, version_id=latest.id, detail='Horizons shot version not found', user=user, access_role=access_role)
            )
        except HTTPException:
            missing_count += 1
            continue
        full_path = resolved.full_path
        if not full_path or not full_path.exists() or not full_path.is_file():
            missing_count += 1
            continue
        entries.append((full_path, tracker_latest_entry_arcname(shot, full_path)))
        included_version_ids.append(latest.id)

    if not entries:
        raise HTTPException(status_code=404, detail='No downloadable latest versions found')

    return entries, missing_count, len(target_shots), included_version_ids


def build_tracker_latest_versions_zip(
    db: Session,
    *,
    project: HorizonProject,
    tracker_id: str,
    tracker_name: str,
    background_tasks: BackgroundTasks,
    user: dict | None = None,
    access_role: str | None = None,
    shot_refs: list[str] | None = None,
    filename: str | None = None,
    share=None,
) -> FileResponse:
    entries, missing_count, requested_count, _included_version_ids = collect_tracker_latest_version_entries(
        db,
        project=project,
        tracker_id=tracker_id,
        user=user,
        access_role=access_role,
        shot_refs=shot_refs,
        share=share,
    )
    response = build_zip_entries(entries, tracker_latest_zip_filename(project, tracker_name, filename), background_tasks)
    response.headers['X-Vueio-Tracker-Zip-Included'] = str(len(entries))
    response.headers['X-Vueio-Tracker-Zip-Skipped'] = str(missing_count)
    response.headers['X-Vueio-Tracker-Zip-Requested'] = str(requested_count)
    return response


def start_tracker_latest_versions_zip_job(
    db: Session,
    *,
    project: HorizonProject,
    tracker_id: str,
    tracker_name: str,
    user: dict | None = None,
    access_role: str | None = None,
    shot_refs: list[str] | None = None,
    filename: str | None = None,
    share=None,
) -> dict:
    entries, missing_count, requested_count, included_version_ids = collect_tracker_latest_version_entries(
        db,
        project=project,
        tracker_id=tracker_id,
        user=user,
        access_role=access_role,
        shot_refs=shot_refs,
        share=share,
    )
    if share is not None:
        owner_type = 'share'
        owner_id = str(share.id)
    else:
        owner_type = 'user'
        owner_id = str((user or {}).get('id') or (user or {}).get('username') or '').strip()
        if not owner_id:
            raise HTTPException(status_code=401, detail='Authentication required')
    job = start_zip_package_job(
        entries,
        tracker_latest_zip_filename(project, tracker_name, filename),
        owner_type=owner_type,
        owner_id=owner_id,
        project_id=project.id,
        authorization={
            'resource_type': 'tracker',
            'tracker_id': tracker_id,
            'version_ids': included_version_ids,
        },
    )
    job['included'] = len(entries)
    job['skipped'] = missing_count
    job['requested'] = requested_count
    return job
