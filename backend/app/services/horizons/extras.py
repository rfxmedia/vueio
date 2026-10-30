"""Extras: files that travel with a shot's versions, such as alpha mattes.

An extra belongs to a shot: its name, note, client visibility and place in the
list. Each version has its own file for it. A version without a file shows the
extra as needed. Adding a version changes no extra; the new version starts
with every extra needed.
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import HorizonShot, HorizonShotExtra, HorizonShotExtraFile, HorizonShotVersion, MediaAsset
from app.services.media import IMAGE_EXTENSIONS, PDF_EXTENSIONS, VIDEO_EXTENSIONS
from app.services.naming import tracker_extra_file_name, tracker_version_file_name

from .version_publication import version_is_published

EXTRA_NAME_MAX_LENGTH = 60
EXTRA_NOTE_MAX_LENGTH = 80
MAX_EXTRAS_PER_SHOT = 100
EXTRA_EVENT_TYPES = frozenset({'extra_added', 'extra_changed', 'extra_removed', 'extra_file_set', 'extra_file_cleared'})


def _clean_text(value: str | None, *, limit: int, label: str) -> str:
    text = ' '.join(str(value or '').split())
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise HTTPException(status_code=400, detail=f'The {label} has characters that are not allowed')
    if len(text) > limit:
        raise HTTPException(status_code=400, detail=f'The {label} can have {limit} characters at most')
    return text


def normalize_extra_name(value: str | None) -> str:
    name = _clean_text(value, limit=EXTRA_NAME_MAX_LENGTH, label='extra name')
    if not name:
        raise HTTPException(status_code=400, detail='Give the extra a name, such as Alpha matte')
    return name


def normalize_extra_note(value: str | None) -> str | None:
    return _clean_text(value, limit=EXTRA_NOTE_MAX_LENGTH, label='note') or None


def numbered_extra_names(extras: list[HorizonShotExtra]) -> dict[str, str]:
    """Extras with the same name are numbered in list order: Alpha matte 1, Alpha matte 2."""
    counts = Counter(extra.name.casefold() for extra in extras)
    seen: Counter = Counter()
    names = {}
    for extra in extras:
        key = extra.name.casefold()
        if counts[key] > 1:
            seen[key] += 1
            names[extra.id] = f'{extra.name} {seen[key]}'
        else:
            names[extra.id] = extra.name
    return names


def _unique_file_name(name: str, used: set[str]) -> str:
    # Windows and macOS treat Matte.mov and matte.mov as the same file.
    candidate, number = name, 2
    path = PurePosixPath(name)
    while candidate.casefold() in used:
        candidate = f'{path.stem} ({number}){path.suffix}'
        number += 1
    used.add(candidate.casefold())
    return candidate


def shot_extras_by_shot(db: Session, shot_ids: list[str]) -> dict[str, list[HorizonShotExtra]]:
    grouped: dict[str, list[HorizonShotExtra]] = {shot_id: [] for shot_id in shot_ids}
    if not shot_ids:
        return grouped
    rows = (
        db.query(HorizonShotExtra)
        .filter(HorizonShotExtra.shot_id.in_(shot_ids))
        .order_by(HorizonShotExtra.sort_order.asc(), HorizonShotExtra.created_at.asc(), HorizonShotExtra.id.asc())
        .all()
    )
    for extra in rows:
        grouped.setdefault(extra.shot_id, []).append(extra)
    return grouped


def extra_files_by_version(db: Session, version_ids: list[str]) -> dict[str, dict[str, HorizonShotExtraFile]]:
    grouped: dict[str, dict[str, HorizonShotExtraFile]] = {version_id: {} for version_id in version_ids}
    if not version_ids:
        return grouped
    for row in db.query(HorizonShotExtraFile).filter(HorizonShotExtraFile.version_id.in_(version_ids)).all():
        grouped.setdefault(row.version_id, {})[row.extra_id] = row
    return grouped


@dataclass(frozen=True)
class VersionExtra:
    """One extra of a version with a file, named as the audience downloads it."""
    extra: HorizonShotExtra
    file: HorizonShotExtraFile
    asset: MediaAsset | None
    name: str
    download_name: str


def visible_extras(extras: list[HorizonShotExtra], *, share: bool) -> list[HorizonShotExtra]:
    return [extra for extra in extras if extra.client_visible] if share else list(extras)


def version_extra_entries(
    shot: HorizonShot,
    version: HorizonShotVersion,
    extras: list[HorizonShotExtra],
    files: dict[str, HorizonShotExtraFile],
    assets: dict[str, MediaAsset],
    *,
    plate_name: str | None,
    share: bool,
) -> list[VersionExtra]:
    """The extras of a version that have a file, in list order.

    Share audiences only see extras that are visible to clients, and only on
    published versions; numbering then counts only what they see.
    """
    if share and not version_is_published(version):
        return []
    shown = visible_extras(extras, share=share)
    names = numbered_extra_names(shown)
    used = {plate_name.casefold()} if plate_name else set()
    entries = []
    for extra in shown:
        file = files.get(extra.id)
        if file is None:
            continue
        asset = assets.get(file.media_asset_id)
        source = PurePosixPath(asset.file_path).name if asset else ''
        download_name = _unique_file_name(tracker_extra_file_name(shot.shot_code, version.label, names[extra.id], source), used)
        entries.append(VersionExtra(extra, file, asset, names[extra.id], download_name))
    return entries


def load_version_extra_entries(db: Session, shot: HorizonShot, version: HorizonShotVersion, *, share: bool) -> list[VersionExtra]:
    extras = shot_extras_by_shot(db, [shot.id])[shot.id]
    files = extra_files_by_version(db, [version.id])[version.id]
    assets = _assets(db, [file.media_asset_id for file in files.values()] + ([version.media_asset_id] if version.media_asset_id else []))
    plate = assets.get(version.media_asset_id) if version.media_asset_id else None
    plate_name = tracker_version_file_name(shot.shot_code, version.label, PurePosixPath(plate.file_path).name) if plate else None
    return version_extra_entries(shot, version, extras, files, assets, plate_name=plate_name, share=share)


def summarize_version_extras(db: Session, version_shots: dict[str, str]) -> dict[str, list[dict]]:
    """Each extra of a version's shot, with that version's file, for compact agent reads.

    Takes {version_id: shot_id}. An extra without a file on the version is
    needed. Versions of shots without extras are left out.
    """
    extras_by_shot = shot_extras_by_shot(db, sorted(set(version_shots.values())))
    files_by_version = extra_files_by_version(db, list(version_shots))
    assets = _assets(db, [row.media_asset_id for files in files_by_version.values() for row in files.values()])
    summaries: dict[str, list[dict]] = {}
    for version_id, shot_id in version_shots.items():
        extras = extras_by_shot.get(shot_id) or []
        if not extras:
            continue
        names = numbered_extra_names(extras)
        files = files_by_version.get(version_id) or {}
        entries = []
        for extra in extras:
            row = files.get(extra.id)
            asset = assets.get(row.media_asset_id) if row else None
            entries.append({
                'id': extra.id,
                'name': names[extra.id],
                'note': extra.note,
                'client_visible': bool(extra.client_visible),
                'needed': row is None,
                'file_path': asset.file_path if asset else None,
                'media_asset_id': row.media_asset_id if row else None,
                'available': bool(asset is not None and asset.unavailable_at is None),
            })
        summaries[version_id] = entries
    return summaries


def _assets(db: Session, asset_ids: list[str]) -> dict[str, MediaAsset]:
    ids = sorted({asset_id for asset_id in asset_ids if asset_id})
    return {asset.id: asset for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(ids)).all()} if ids else {}


def _file_flags(file_name: str) -> dict:
    extension = PurePosixPath(file_name).suffix.lower()
    return {
        'extension': extension.lstrip('.'),
        'is_video': extension in VIDEO_EXTENSIONS,
        'is_image': extension in IMAGE_EXTENSIONS,
        'is_pdf': extension in PDF_EXTENSIONS,
    }


def serialize_tracker_extras(
    db: Session,
    shots: list[HorizonShot],
    versions_by_shot: dict[str, list[HorizonShotVersion]],
    assets: dict[str, MediaAsset],
    *,
    share: bool = False,
) -> tuple[dict[str, list[dict]], dict[str, list[dict]], dict[str, str | None]]:
    """Extras of each shot, and the files of each version, for tracker payloads.

    Returns ({shot_id: [extra]}, {version_id: [file]}, {version_id: plate
    download name}). Share audiences get only client-visible extras on
    published versions, without team fields.
    """
    shot_ids = [shot.id for shot in shots]
    extras_by_shot = shot_extras_by_shot(db, shot_ids)
    version_ids = [version.id for versions in versions_by_shot.values() for version in versions]
    files_by_version = extra_files_by_version(db, version_ids)
    missing = [file.media_asset_id for files in files_by_version.values() for file in files.values() if file.media_asset_id not in assets]
    assets = {**assets, **_assets(db, missing)}

    shot_payloads: dict[str, list[dict]] = {}
    version_payloads: dict[str, list[dict]] = {}
    plate_names: dict[str, str | None] = {}
    for shot in shots:
        extras = visible_extras(extras_by_shot.get(shot.id, []), share=share)
        names = numbered_extra_names(extras)
        shot_payloads[shot.id] = [
            {'id': extra.id, 'name': names[extra.id], 'base_name': extra.name, 'note': extra.note,
             **({} if share else {'client_visible': bool(extra.client_visible)})}
            for extra in extras
        ]
        for version in versions_by_shot.get(shot.id, []):
            plate = assets.get(version.media_asset_id) if version.media_asset_id else None
            plate_name = tracker_version_file_name(shot.shot_code, version.label, PurePosixPath(plate.file_path).name) if plate else None
            plate_names[version.id] = plate_name
            entries = version_extra_entries(
                shot, version, extras_by_shot.get(shot.id, []), files_by_version.get(version.id, {}), assets,
                plate_name=plate_name, share=share,
            )
            version_payloads[version.id] = [_serialize_entry(entry, share=share) for entry in entries]
    return shot_payloads, version_payloads, plate_names


def _serialize_entry(entry: VersionExtra, *, share: bool) -> dict:
    asset = entry.asset
    file_name = PurePosixPath(asset.file_path).name if asset else ''
    payload = {
        'extra_id': entry.extra.id,
        'name': entry.name,
        'note': entry.extra.note,
        'download_name': entry.download_name,
        'file_name': file_name,
        'media_asset_id': entry.file.media_asset_id,
        'horizons_media_asset_id': entry.file.media_asset_id,
        'media_entity_type': 'media_asset',
        'media_entity_key': f'asset:{entry.file.media_asset_id}',
        'exists': bool(asset is not None and asset.unavailable_at is None),
        'file_size': asset.file_size if asset else None,
        **_file_flags(file_name),
    }
    if not share:
        payload.update({
            'client_visible': bool(entry.extra.client_visible),
            'path': asset.file_path if asset else None,
            'created_by': entry.file.created_by,
            'updated_at': entry.file.updated_at,
        })
    return payload


def delete_extra_files_for_versions(db: Session, version_ids: list[str]) -> None:
    if version_ids:
        db.query(HorizonShotExtraFile).filter(HorizonShotExtraFile.version_id.in_(version_ids)).delete(synchronize_session=False)


def delete_extras_for_shots(db: Session, shot_ids: list[str]) -> None:
    if shot_ids:
        db.query(HorizonShotExtraFile).filter(HorizonShotExtraFile.shot_id.in_(shot_ids)).delete(synchronize_session=False)
        db.query(HorizonShotExtra).filter(HorizonShotExtra.shot_id.in_(shot_ids)).delete(synchronize_session=False)


def copy_extras_for_shot(db: Session, source_shot_id: str, target_shot: HorizonShot, version_map: dict[str, str], now: float) -> None:
    """Copy a shot's extras and their files to a duplicated shot."""
    extras = shot_extras_by_shot(db, [source_shot_id])[source_shot_id]
    files = db.query(HorizonShotExtraFile).filter(HorizonShotExtraFile.shot_id == source_shot_id).all()
    extra_map = {}
    for extra in extras:
        extra_map[extra.id] = str(uuid.uuid4())
        db.add(HorizonShotExtra(
            id=extra_map[extra.id], project_id=target_shot.project_id, tracker_id=target_shot.tracker_id,
            shot_id=target_shot.id, name=extra.name, note=extra.note, client_visible=extra.client_visible,
            sort_order=extra.sort_order, created_by=extra.created_by, created_at=extra.created_at, updated_at=now,
        ))
    for file in files:
        if file.extra_id in extra_map and file.version_id in version_map:
            db.add(HorizonShotExtraFile(
                id=str(uuid.uuid4()), project_id=target_shot.project_id, tracker_id=target_shot.tracker_id,
                shot_id=target_shot.id, extra_id=extra_map[file.extra_id], version_id=version_map[file.version_id],
                media_asset_id=file.media_asset_id, created_by=file.created_by, created_at=file.created_at, updated_at=now,
            ))


def shared_extra_uses(db: Session, project_id: str, asset_id: str) -> list[tuple[HorizonShotExtra, HorizonShotVersion]]:
    """Every extra that uses this file, with the version it belongs to."""
    return (
        db.query(HorizonShotExtra, HorizonShotVersion)
        .join(HorizonShotExtraFile, HorizonShotExtraFile.extra_id == HorizonShotExtra.id)
        .join(HorizonShotVersion, HorizonShotVersion.id == HorizonShotExtraFile.version_id)
        .filter(HorizonShotExtraFile.project_id == project_id)
        .filter(HorizonShotExtraFile.media_asset_id == asset_id)
        .all()
    )


EXTRA_COMPARISON_PREFIX = 'extra-'


def comparison_extra_file(db: Session, version_id: str, other_id: str) -> HorizonShotExtraFile | None:
    """For a comparison of a version with one of its extras, `other_id` is extra-<extra id>."""
    if not other_id.startswith(EXTRA_COMPARISON_PREFIX):
        return None
    row = (
        db.query(HorizonShotExtraFile)
        .filter(HorizonShotExtraFile.extra_id == other_id[len(EXTRA_COMPARISON_PREFIX):])
        .filter(HorizonShotExtraFile.version_id == version_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail='This version has no file for this extra')
    return row


def is_extra_only_asset(db: Session, project_id: str, asset_id: str) -> bool:
    """A file used as an extra and as no version's plate, such as a matte."""
    used_as_extra = db.query(HorizonShotExtraFile.id).filter(
        HorizonShotExtraFile.project_id == project_id, HorizonShotExtraFile.media_asset_id == asset_id,
    ).first() is not None
    return used_as_extra and db.query(HorizonShotVersion.id).filter(
        HorizonShotVersion.project_id == project_id, HorizonShotVersion.media_asset_id == asset_id,
    ).first() is None
