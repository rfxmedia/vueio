from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.models import HorizonShot, HorizonShotVersion


@dataclass
class ShotCommandActor:
    user: dict | None
    auth_mode: str | None
    source: str
    actor_id: str | None
    actor_name: str


@dataclass
class ShotCommandContext:
    project_id: str
    tracker_id: str
    tracker_name: str | None
    access_role: str
    actor: ShotCommandActor
    can_create_shot: bool
    can_update_shot: bool
    can_delete_shot: bool
    can_delete_versions: bool
    can_archive_shot: bool
    restricted_artist: bool
    allowed_media_prefix: str | None = None
    event_mode: Literal['full', 'none'] = 'full'
    activity_enabled: bool = False


@dataclass
class ShotCommandResult:
    shots: list[HorizonShot] = field(default_factory=list)
    versions: list[HorizonShotVersion] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    stats_dirty_tracker_ids: set[str] = field(default_factory=set)
    activity_records: list[dict] = field(default_factory=list)
    queued_media_paths: list[str] = field(default_factory=list)
    deleted: list[dict] = field(default_factory=list)
    response_hint: dict = field(default_factory=dict)

    def extend(self, other: 'ShotCommandResult') -> 'ShotCommandResult':
        self.shots.extend(other.shots)
        self.versions.extend(other.versions)
        self.events.extend(other.events)
        self.stats_dirty_tracker_ids.update(other.stats_dirty_tracker_ids)
        self.activity_records.extend(other.activity_records)
        self.queued_media_paths.extend(path for path in other.queued_media_paths if path not in self.queued_media_paths)
        self.deleted.extend(other.deleted)
        self.response_hint.update(other.response_hint)
        return self
