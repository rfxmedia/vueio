from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import NotificationDelivery, NotificationSubscription
from app.services.auth import (
    get_request_user,
    get_user_from_session,
    require_admin,
    require_signed_in_user,
)
from app.services.notifications import (
    create_subscription,
    delete_subscription,
    get_discord_provider_settings,
    list_notification_feed,
    mark_notification_read,
    save_notification_preferences,
    save_discord_provider_settings,
    send_subscription_test,
    serialize_delivery,
    serialize_notification_preferences,
    serialize_subscription,
    update_subscription,
)

router = APIRouter(tags=['notifications'])
logger = logging.getLogger(__name__)


class NotificationReadRequest(BaseModel):
    event_id: Optional[int] = Field(None, description='Mark events up to and including this event as read. Without it, every event up to now is marked read.')
    scope: Optional[str] = Field(None, description="'related_to_me', 'all_visible' or 'default'. Without it, your default scope is used.")
    filter: Optional[str] = Field(None, description="'all', 'comments', 'status', 'assignments', 'versions', 'downloads', 'updates' or one event type. Default 'all'.")


class NotificationPreferencesUpdate(BaseModel):
    default_scope: Optional[str] = Field(None, description="'related_to_me' (shots assigned to you) or 'all_visible'. 'default' uses the default for your role.")
    event_types: Optional[list[str]] = Field(None, description="Event types or groups ('comments', 'status', 'assignments', 'versions', 'downloads', 'updates') to receive. An empty list means all. Replaces the saved list.")
    channels: Optional[dict[str, bool]] = Field(None, description="Channels to turn on or off, for example {'discord': false}. Keys: in_app, discord, email, telegram, whatsapp. Channels that you leave out keep their value.")


class NotificationSubscriptionCreate(BaseModel):
    provider: str = Field('discord', description="Only 'discord', the default.")
    recipient_user_id: str = Field(description='The user whose project access and notification preferences select the events.')
    destination: str = Field(description='Discord channel id (digits only).')
    # None keeps the recipient's role default, which an admin recipient relies on.
    scope: Optional[str] = Field(None, description="'related_to_me' (shots assigned to the recipient) or 'all_visible'. If you leave it out, an admin recipient gets 'all_visible' and others get 'related_to_me'.")
    project_filters: Optional[list[str]] = Field(None, description='Project ids. Empty means all projects.')
    event_filters: Optional[list[str]] = Field(None, description="Event types or groups ('comments', 'status', 'assignments', 'versions', 'downloads', 'updates'). Empty means all.")
    config: Optional[dict] = Field(None, description="Extra options. {'mention_everyone': true} adds @everyone to the Discord message.")
    is_enabled: bool = True


class NotificationSubscriptionUpdate(BaseModel):
    provider: Optional[str] = Field(None, description="Only 'discord'.")
    recipient_user_id: Optional[str] = Field(None, description='The user whose project access and notification preferences select the events.')
    destination: Optional[str] = Field(None, description='Discord channel id (digits only).')
    scope: Optional[str] = Field(None, description="'related_to_me' (shots assigned to the recipient) or 'all_visible'.")
    project_filters: Optional[list[str]] = Field(None, description='Project ids. Empty means all projects. Replaces the saved list.')
    event_filters: Optional[list[str]] = Field(None, description="Event types or groups ('comments', 'status', 'assignments', 'versions', 'downloads', 'updates'). Empty means all. Replaces the saved list.")
    config: Optional[dict] = Field(None, description="Extra options. Replaces the saved options. {'mention_everyone': true} adds @everyone to the Discord message.")
    is_enabled: Optional[bool] = None


class DiscordProviderSettingsUpdate(BaseModel):
    application_id: Optional[str] = Field(None, description='Discord application id, digits only. Used to make the bot invite link.')
    public_base_url: Optional[str] = Field(None, description='The http or https address of this Vue.io server. Used for links in messages.')
    bot_token: Optional[str] = Field(None, description='Discord bot token. Leave it out to keep the saved token.')
    clear_token: bool = Field(False, description='True removes the saved token. Do not send it with a new bot_token.')


def _require_admin_session(vueio_session: str | None) -> dict:
    return require_admin(vueio_session)


@router.get('/api/notifications/feed', summary='List my notifications')
def get_notifications_feed(
    limit: int = 40,
    calendar_days: int | None = None,
    before_created_at: float | None = None,
    before_id: int | None = None,
    filter: str | None = None,
    scope: str | None = None,
    read_status: str | None = None,
    vueio_session: str | None = Cookie(None),
    x_vueio_agent_key: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """List your notifications, which are tracker events, newest first.

    `scope` is 'related_to_me' (shots assigned to you), 'all_visible' or
    'default'. `filter` is 'all', 'comments', 'status', 'assignments',
    'versions', 'downloads', 'updates' or one event type. `read_status` is
    'all', 'unread' or 'read'. `limit` is 1 to 100. `calendar_days` (0 to 14)
    stops the page after that many days. For the next page, send
    `next_before_created_at` and `next_before_id` as `before_created_at` and
    `before_id`.
    """
    user, auth_mode = get_request_user(vueio_session, x_vueio_agent_key)
    return list_notification_feed(
        db,
        user=user,
        auth_mode=auth_mode,
        limit=limit,
        calendar_days=calendar_days,
        before_created_at=before_created_at,
        before_id=before_id,
        filter_value=filter,
        scope=scope,
        read_status=read_status,
    )


@router.post('/api/notifications/read', summary='Mark notifications read')
def post_notifications_read(
    data: NotificationReadRequest,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """Mark notifications as read up to one event, or up to now.

    The read position is kept for each scope and filter pair, so marking one
    feed does not change the others. The result is the new read position.
    `last_seen_event_id` is empty when you mark up to now.
    """
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    return mark_notification_read(db, user, event_id=data.event_id, scope=data.scope, filter_value=data.filter)


@router.get('/api/me/notification-preferences', summary='Get my notification settings')
def get_my_notification_preferences(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    """Return your default scope, event types and channels for notifications.

    An empty `event_types` list means all events.
    """
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    user_id = user.get('id') or user.get('username')
    from app.services.notifications import get_notification_preferences
    return serialize_notification_preferences(get_notification_preferences(db, user_id, user), user_id, user)


@router.put('/api/me/notification-preferences', summary='Update my notification settings')
def put_my_notification_preferences(
    data: NotificationPreferencesUpdate,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """Change your notification settings.

    Fields that you leave out keep their value. With the in_app channel off,
    the notification feed is empty.
    """
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    return save_notification_preferences(db, user, data.model_dump(exclude_unset=True))


@router.get('/api/admin/notification-subscriptions', summary='List notification subscriptions')
def get_admin_notification_subscriptions(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    """List every notification subscription, newest first.

    A subscription sends the tracker activity that one user can see to a
    Discord channel.
    """
    _require_admin_session(vueio_session)
    subscriptions = db.query(NotificationSubscription).order_by(NotificationSubscription.created_at.desc()).all()
    return {'subscriptions': [serialize_subscription(subscription) for subscription in subscriptions]}


@router.get('/api/admin/notification-providers/discord', summary='Get Discord settings')
def get_admin_discord_provider_settings(vueio_session: str | None = Cookie(None)):
    """Return the Discord bot settings for notifications.

    The bot token is never returned. `is_configured` and `has_saved_token` tell
    whether a token is set. `invite_url` adds the bot to a Discord server.
    """
    _require_admin_session(vueio_session)
    return get_discord_provider_settings()


@router.put('/api/admin/notification-providers/discord', summary='Update Discord settings')
def put_admin_discord_provider_settings(
    data: DiscordProviderSettingsUpdate,
    vueio_session: str | None = Cookie(None),
):
    """Change the Discord bot settings for notifications.

    Fields that you leave out keep their value. When a token is set, the server
    starts sending queued Discord messages. Agent keys cannot change these
    settings because they hold the bot token.
    """
    # The bot token is a credential: only a signed-in person may set it.
    require_signed_in_user(vueio_session)
    _require_admin_session(vueio_session)
    return save_discord_provider_settings(data.model_dump(exclude_unset=True))


@router.post('/api/admin/notification-subscriptions', summary='Add a notification subscription')
def post_admin_notification_subscription(
    data: NotificationSubscriptionCreate,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """Send tracker activity that one user can see to a Discord channel.

    New events that match the filters are sent. Past events are not sent.
    Fields that you leave out get their default.
    """
    user = _require_admin_session(vueio_session)
    return {'subscription': create_subscription(db, data=data.model_dump(), created_by=user.get('id') or user.get('username'))}


@router.put('/api/admin/notification-subscriptions/{subscription_id}', summary='Update a notification subscription')
def put_admin_notification_subscription(
    subscription_id: str,
    data: NotificationSubscriptionUpdate,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """Change a notification subscription.

    Fields that you leave out keep their value.
    """
    _require_admin_session(vueio_session)
    return {'subscription': update_subscription(db, subscription_id, data.model_dump(exclude_unset=True))}


@router.delete('/api/admin/notification-subscriptions/{subscription_id}', summary='Delete a notification subscription')
def delete_admin_notification_subscription(subscription_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    """Delete a notification subscription and its delivery history.

    Messages that are not sent yet are also deleted. This is permanent.
    """
    _require_admin_session(vueio_session)
    delete_subscription(db, subscription_id)
    return {'status': 'deleted'}


@router.post('/api/admin/notification-subscriptions/{subscription_id}/test', summary='Send a test notification')
def test_admin_notification_subscription(subscription_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    """Send a test message to the Discord channel of a subscription now.

    The test is sent even when the subscription is off. It is not recorded as a
    delivery.
    """
    _require_admin_session(vueio_session)
    subscription = db.query(NotificationSubscription).filter(NotificationSubscription.id == subscription_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail='Notification subscription not found')
    try:
        send_subscription_test(subscription)
    except Exception as exc:
        logger.warning('Notification test failed (%s)', type(exc).__name__)
        raise HTTPException(status_code=400, detail='Notification test failed') from exc
    return {'status': 'sent'}


@router.get('/api/admin/notification-deliveries', summary='List notification deliveries')
def get_admin_notification_deliveries(
    limit: int = 100,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """List Discord notification messages, sent and queued, newest first.

    `limit` is 1 to 250. `status` is 'pending', 'sending', 'sent' or 'failed'.
    Each delivery has its attempt count and the event payload.
    """
    _require_admin_session(vueio_session)
    deliveries = (
        db.query(NotificationDelivery)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(max(1, min(limit, 250)))
        .all()
    )
    return {'deliveries': [serialize_delivery(delivery) for delivery in deliveries]}
