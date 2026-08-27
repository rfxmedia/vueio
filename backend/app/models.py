from __future__ import annotations

import time

from sqlalchemy import BigInteger, Boolean, Column, Float, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, deferred

Base = declarative_base()


class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, index=True)
    project_id = Column(String, index=True, nullable=True)
    horizons_media_asset_id = Column(String, index=True, nullable=True)
    horizons_shot_version_id = Column(String, index=True, nullable=True)
    user_name = Column(String)
    timestamp = Column(Float)
    text = Column(Text)
    resolved = Column(Boolean, default=False)
    created_at = Column(Float, default=time.time)
    parent_comment_id = Column(Integer, index=True, nullable=True)
    root_comment_id = Column(Integer, index=True, nullable=True)
    annotation_data = Column(Text, nullable=True)
    annotation_target = Column(Text, nullable=True)
    attachments_data = Column(Text, nullable=True)


class ShareLink(Base):
    __tablename__ = 'shares'
    id = Column(String, primary_key=True)
    path = Column(String)
    is_folder = Column(Boolean, default=False)
    share_type = Column(String, default='file')
    project_id = Column(String, nullable=True)
    tracker_id = Column(String, nullable=True)
    tracker_name = Column(String, nullable=True)
    page_id = Column(String, nullable=True)
    media_asset_id = Column(String, nullable=True, index=True)
    created_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    expires_at = Column(Float, nullable=True)
    password_hash = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    access_count = Column(Integer, default=0)
    last_accessed = Column(Float, nullable=True)
    allow_download = Column(Boolean, default=False)
    allow_upload = Column(Boolean, default=False)
    request_files = Column(Boolean, nullable=False, default=False)


class TranscodeJob(Base):
    __tablename__ = 'transcodes'
    id = Column(Integer, primary_key=True)
    file_path = Column(String, unique=True, index=True)
    status = Column(String, default='pending')
    output_path = Column(String, nullable=True)
    progress = Column(Float, default=0)
    duration = Column(Float, default=0)
    created_at = Column(Float, default=time.time)
    last_accessed = Column(Float, nullable=True, index=True, default=time.time)


class UploadSession(Base):
    __tablename__ = 'upload_sessions'
    id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False, index=True)
    share_id = Column(String, nullable=True, index=True)
    project_id = Column(String, nullable=True, index=True)
    owner_user_id = Column(String, nullable=True, index=True)
    base_path = Column(String, nullable=False, default='')
    uploader_name = Column(String, nullable=False)
    client_batch_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default='active')
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    last_activity_at = Column(Float, default=time.time)
    expires_at = Column(Float, nullable=True, index=True)


class UploadItem(Base):
    __tablename__ = 'upload_items'
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    rel_path = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    mime_type = Column(String, nullable=True)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    bytes_received = Column(BigInteger, nullable=False, default=0)
    temp_path = Column(String, nullable=True)
    final_path = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default='pending')
    error_text = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    completed_at = Column(Float, nullable=True, index=True)


class PackageJob(Base):
    __tablename__ = 'package_jobs'
    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False, default='zip')
    status = Column(String, nullable=False, default='queued', index=True)
    filename = Column(String, nullable=False)
    artifact_path = Column(String, nullable=True)
    total_bytes = Column(BigInteger, nullable=False, default=0)
    packaged_bytes = Column(BigInteger, nullable=False, default=0)
    file_count = Column(Integer, nullable=False, default=0)
    packaged_files = Column(Integer, nullable=False, default=0)
    progress = Column(Float, nullable=False, default=0)
    message = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    owner_type = Column(String, nullable=False, index=True)
    owner_id = Column(String, nullable=False, index=True)
    project_id = Column(String, nullable=True, index=True)
    authorization_json = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    updated_at = Column(Float, nullable=False, default=time.time, index=True)
    expires_at = Column(Float, nullable=False, index=True)


class ActivityLog(Base):
    """Compatibility model for installations created before route telemetry was removed."""

    __tablename__ = 'activity_log'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    user_name = Column(String, nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    entity_title = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)


class TrackerEvent(Base):
    __tablename__ = 'tracker_events'
    __table_args__ = (
        Index('uq_tracker_events_undo_of_event_id', 'undo_of_event_id', unique=True),
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    tracker_id = Column(String, nullable=False, index=True)
    shot_id = Column(String, nullable=True, index=True)
    shot_version_id = Column(String, nullable=True, index=True)
    comment_id = Column(String, nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=True)
    actor_name = Column(String, nullable=False)
    source = Column(String, nullable=False, default='app')
    payload_json = Column(Text, nullable=True)
    undo_of_event_id = Column(Integer, nullable=True)
    state_snapshot = deferred(Column(LargeBinary, nullable=True))
    state_hash = Column(String, nullable=True)
    created_at = Column(Float, default=time.time, index=True)


class TrackerViewEvent(Base):
    __tablename__ = 'tracker_view_events'
    __table_args__ = (
        Index('ix_tracker_view_events_history', 'project_id', 'tracker_id', 'created_at'),
        Index('ix_tracker_view_events_presence', 'project_id', 'tracker_id', 'event_type', 'last_seen_at'),
        Index('ix_tracker_view_events_visit', 'project_id', 'tracker_id', 'visit_id'),
        Index('ix_tracker_view_events_created_at', 'created_at'),
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(String, nullable=False)
    tracker_id = Column(String, nullable=False)
    shot_id = Column(String, nullable=True)
    shot_version_id = Column(String, nullable=True)
    visit_id = Column(String, nullable=False)
    viewer_user_id = Column(String, nullable=True)
    viewer_name = Column(String, nullable=False)
    source = Column(String, nullable=False, default='app')
    share_id = Column(String, nullable=True)
    event_type = Column(String, nullable=False)
    device_type = Column(String, nullable=False, default='desktop')
    client_metadata_json = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False, default=time.time)
    last_seen_at = Column(Float, nullable=False, default=time.time)


class DownloadEvent(Base):
    __tablename__ = 'download_events'
    id = Column(String, primary_key=True)
    created_at = Column(Float, default=time.time, index=True)
    user_id = Column(String, nullable=True, index=True)
    user_name = Column(String, nullable=True)
    source = Column(String, nullable=False, default='app', index=True)
    auth_mode = Column(String, nullable=True)
    share_id = Column(String, nullable=True, index=True)
    project_id = Column(String, nullable=True, index=True)
    tracker_id = Column(String, nullable=True)
    event_type = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False, index=True)
    resource_id = Column(String, nullable=True)
    resource_name = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    paths_json = Column(Text, nullable=False, default='[]')
    size_bytes = Column(BigInteger, nullable=True)
    status = Column(String, nullable=False, default='started')
    ip_address = Column(String, nullable=True, index=True)
    ip_chain_json = Column(Text, nullable=False, default='{}')
    geo_json = Column(Text, nullable=False, default='{}')
    device_json = Column(Text, nullable=False, default='{}')
    request_json = Column(Text, nullable=False, default='{}')
    client_json = Column(Text, nullable=False, default='{}')
    metadata_json = Column(Text, nullable=False, default='{}')


class RecentlyViewed(Base):
    __tablename__ = 'recently_viewed'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    item_type = Column(String, nullable=False)
    item_id = Column(String, nullable=False)
    project_id = Column(String, nullable=True)
    title = Column(String, nullable=True)
    subtitle = Column(String, nullable=True)
    viewed_at = Column(Float, default=time.time)


class AppTheme(Base):
    __tablename__ = 'app_theme'
    id = Column(Integer, primary_key=True)
    colors_json = Column(Text, nullable=False, default='{}')
    updated_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class AppIdentity(Base):
    __tablename__ = 'app_identity'
    id = Column(Integer, primary_key=True)
    team_name = Column(String, nullable=False, default='Vue')
    website_url = Column(String, nullable=True)
    logo_upload_name = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class UserSession(Base):
    __tablename__ = 'user_sessions'
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    created_at = Column(Float, default=time.time)
    last_accessed = Column(Float, default=time.time)
    expires_at = Column(Float, nullable=False, index=True)


class UserPreference(Base):
    __tablename__ = 'user_preferences'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, unique=True, index=True)
    mc_layout = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class MediaAsset(Base):
    __tablename__ = 'media_assets'
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    file_path = Column(String, nullable=False)
    storage_scope = Column(String, nullable=False, default='project')
    content_hash = Column(String, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    modified_at = Column(Float, nullable=True)
    source_signature = Column(String, nullable=True, index=True)
    artifact_identity = Column(String, nullable=True)
    unavailable_at = Column(Float, nullable=True, index=True)
    unavailable_reason = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class MediaMetadata(Base):
    __tablename__ = 'media_metadata'
    cache_identity = Column(String, primary_key=True)
    media_asset_id = Column(String, nullable=True, index=True)
    file_path = Column(String, nullable=False)
    file_size = Column(BigInteger, nullable=True)
    modified_at = Column(Float, nullable=True)
    info_json = Column(Text, nullable=False)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class FileOperationJournal(Base):
    __tablename__ = 'file_operation_journal'
    id = Column(String, primary_key=True)
    operation_type = Column(String, nullable=False, index=True)
    project_id = Column(String, nullable=False, index=True)
    source_path = Column(String, nullable=True)
    destination_path = Column(String, nullable=True)
    status = Column(String, nullable=False, default='pending', index=True)
    payload_json = Column(Text, nullable=False, default='{}')
    error_text = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class VersionRegistryEntry(Base):
    __tablename__ = 'version_registry'
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    tracker_id = Column(String, nullable=True)
    tracker_name = Column(String, nullable=False, index=True)
    shot_id = Column(String, nullable=False, index=True)
    variant_id = Column(String, nullable=True, index=True)
    version_number = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    media_asset_id = Column(String, nullable=True, index=True)
    source = Column(String, nullable=False, default='tracker_json')
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class ShotRegistryEntry(Base):
    __tablename__ = 'shot_registry'
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    tracker_id = Column(String, nullable=True, index=True)
    tracker_name = Column(String, nullable=False, index=True)
    shot_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default='not_started')
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    latest_version_number = Column(Integer, nullable=True)
    latest_file_path = Column(String, nullable=True)
    latest_media_asset_id = Column(String, nullable=True, index=True)
    source = Column(String, nullable=False, default='tracker_json')
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class HorizonProject(Base):
    __tablename__ = 'horizons_projects'
    id = Column(String, primary_key=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default='active')
    visibility = Column(String, nullable=False, default='private')
    created_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    due_date = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)
    storage_root = Column(String, nullable=False, default='data', server_default='data', index=True)
    storage_path = Column(String, nullable=True)


class HorizonProjectGrant(Base):
    __tablename__ = 'horizons_project_grants'
    __table_args__ = (
        UniqueConstraint('project_id', 'subject_type', 'subject_id', name='idx_horizons_grants_unique'),
    )

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    subject_type = Column(String, nullable=False)
    subject_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, default='viewer')
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class HorizonPage(Base):
    __tablename__ = 'horizons_pages'
    __table_args__ = (
        UniqueConstraint('project_id', 'slug', name='idx_horizons_pages_project_slug'),
    )

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    cover_path = Column(String, nullable=True)
    blocks_json = Column(Text, nullable=False, default='[]')
    created_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class HorizonTracker(Base):
    __tablename__ = 'horizons_trackers'
    __table_args__ = (
        UniqueConstraint('project_id', 'slug', name='idx_horizons_trackers_project_slug'),
    )

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    settings_json = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=True)
    stats_json = Column(Text, nullable=True)
    stats_updated_at = Column(Float, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class HorizonShot(Base):
    __tablename__ = 'horizons_shots'
    __table_args__ = (
        UniqueConstraint('tracker_id', 'shot_code', name='idx_horizons_shots_tracker_code'),
    )

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    tracker_id = Column(String, nullable=False, index=True)
    shot_code = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default='not_started')
    category = Column(String, nullable=True)
    assignee_user_id = Column(String, nullable=True, index=True)
    latest_version_label = Column(String, nullable=True)
    latest_media_asset_id = Column(String, nullable=True, index=True)
    archived_at = Column(Float, nullable=True, index=True)
    archived_by = Column(String, nullable=True)
    archive_reason = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class HorizonShotAssignee(Base):
    __tablename__ = 'horizons_shot_assignees'
    __table_args__ = (
        UniqueConstraint('shot_id', 'user_id', name='uq_horizon_shot_assignee_user'),
    )

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    tracker_id = Column(String, nullable=False, index=True)
    shot_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class HorizonShotVersion(Base):
    __tablename__ = 'horizons_shot_versions'
    __table_args__ = (
        UniqueConstraint('shot_id', 'label', name='idx_horizons_versions_shot_label'),
    )

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    tracker_id = Column(String, nullable=False, index=True)
    shot_id = Column(String, nullable=False, index=True)
    label = Column(String, nullable=False)
    media_asset_id = Column(String, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    share_state = Column(String, nullable=False, default='published')
    published_at = Column(Float, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class AgentApiKey(Base):
    __tablename__ = 'agent_api_keys'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    user_id = Column(String, nullable=False, index=True)
    key_prefix = Column(String, nullable=False, index=True)
    secret_hash = Column(String, nullable=False, unique=True, index=True)
    encrypted_token = Column(Text, nullable=True)
    scopes_json = Column(Text, nullable=False, default='[]')
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    last_used_at = Column(Float, nullable=True)
    revoked_at = Column(Float, nullable=True)


class AgentMutationReceipt(Base):
    __tablename__ = 'agent_mutation_receipts'
    __table_args__ = (
        UniqueConstraint('agent_key_id', 'operation', 'idempotency_key', name='uq_agent_mutation_receipts_key_operation_idempotency'),
    )
    id = Column(String, primary_key=True)
    agent_key_id = Column(String, nullable=False, index=True)
    operation = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False, index=True)
    response_json = Column(Text, nullable=False)
    created_at = Column(Float, default=time.time)


class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    user_id = Column(String, primary_key=True)
    default_scope = Column(String, nullable=False, default='related_to_me')
    event_types_json = Column(Text, nullable=False, default='[]')
    channels_json = Column(Text, nullable=False, default='{}')
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class NotificationReadState(Base):
    __tablename__ = 'notification_read_state'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    feed_key = Column(String, nullable=False, default='default')
    last_seen_event_id = Column(Integer, nullable=True)
    last_seen_created_at = Column(Float, nullable=False, default=0)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    __table_args__ = (
        UniqueConstraint('user_id', 'feed_key', name='uq_notification_read_state_user_feed'),
    )


class NotificationSubscription(Base):
    __tablename__ = 'notification_subscriptions'
    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False, index=True)
    recipient_user_id = Column(String, nullable=False, index=True)
    destination = Column(String, nullable=False)
    scope = Column(String, nullable=False, default='related_to_me')
    project_filters_json = Column(Text, nullable=False, default='[]')
    event_filters_json = Column(Text, nullable=False, default='[]')
    config_json = Column(Text, nullable=False, default='{}')
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)


class NotificationDelivery(Base):
    __tablename__ = 'notification_deliveries'
    id = Column(String, primary_key=True)
    tracker_event_id = Column(Integer, nullable=False, index=True)
    recipient_user_id = Column(String, nullable=False, index=True)
    subscription_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default='pending', index=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(Float, nullable=True, index=True)
    sent_at = Column(Float, nullable=True)
    last_error = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False, default='{}')
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time)
    __table_args__ = (
        UniqueConstraint('tracker_event_id', 'subscription_id', 'recipient_user_id', name='uq_notification_delivery_event_subscription_recipient'),
    )
