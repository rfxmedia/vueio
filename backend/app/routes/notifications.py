from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import NotificationDelivery, NotificationSubscription
from app.services.auth import (
    get_request_user,
    get_user_from_session,
    require_admin,
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
    event_id: Optional[int] = None
    scope: Optional[str] = None
    filter: Optional[str] = None


class NotificationPreferencesUpdate(BaseModel):
    default_scope: Optional[str] = None
    event_types: Optional[list[str]] = None
    channels: Optional[dict[str, bool]] = None


class NotificationSubscriptionCreate(BaseModel):
    provider: str = 'discord'
    recipient_user_id: str
    destination: str
    scope: str = 'related_to_me'
    project_filters: Optional[list[str]] = None
    event_filters: Optional[list[str]] = None
    config: Optional[dict] = None
    is_enabled: bool = True


class NotificationSubscriptionUpdate(BaseModel):
    provider: Optional[str] = None
    recipient_user_id: Optional[str] = None
    destination: Optional[str] = None
    scope: Optional[str] = None
    project_filters: Optional[list[str]] = None
    event_filters: Optional[list[str]] = None
    config: Optional[dict] = None
    is_enabled: Optional[bool] = None


class DiscordProviderSettingsUpdate(BaseModel):
    application_id: Optional[str] = None
    public_base_url: Optional[str] = None
    bot_token: Optional[str] = None
    clear_token: bool = False


def _require_admin_session(vueio_session: str | None) -> dict:
    return require_admin(vueio_session)


@router.get('/api/notifications/feed')
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


@router.post('/api/notifications/read')
def post_notifications_read(
    data: NotificationReadRequest,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    return mark_notification_read(db, user, event_id=data.event_id, scope=data.scope, filter_value=data.filter)


@router.get('/api/me/notification-preferences')
def get_my_notification_preferences(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    user_id = user.get('id') or user.get('username')
    from app.services.notifications import get_notification_preferences
    return serialize_notification_preferences(get_notification_preferences(db, user_id, user), user_id, user)


@router.put('/api/me/notification-preferences')
def put_my_notification_preferences(
    data: NotificationPreferencesUpdate,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    user = get_user_from_session(vueio_session)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    return save_notification_preferences(db, user, data.model_dump(exclude_unset=True))


@router.get('/api/admin/notification-subscriptions')
def get_admin_notification_subscriptions(vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    subscriptions = db.query(NotificationSubscription).order_by(NotificationSubscription.created_at.desc()).all()
    return {'subscriptions': [serialize_subscription(subscription) for subscription in subscriptions]}


@router.get('/api/admin/notification-providers/discord')
def get_admin_discord_provider_settings(vueio_session: str | None = Cookie(None)):
    _require_admin_session(vueio_session)
    return get_discord_provider_settings()


@router.put('/api/admin/notification-providers/discord')
def put_admin_discord_provider_settings(
    data: DiscordProviderSettingsUpdate,
    vueio_session: str | None = Cookie(None),
):
    _require_admin_session(vueio_session)
    return save_discord_provider_settings(data.model_dump(exclude_unset=True))


@router.post('/api/admin/notification-subscriptions')
def post_admin_notification_subscription(
    data: NotificationSubscriptionCreate,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    user = _require_admin_session(vueio_session)
    return {'subscription': create_subscription(db, data=data.model_dump(exclude_unset=True), created_by=user.get('id') or user.get('username'))}


@router.put('/api/admin/notification-subscriptions/{subscription_id}')
def put_admin_notification_subscription(
    subscription_id: str,
    data: NotificationSubscriptionUpdate,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    _require_admin_session(vueio_session)
    return {'subscription': update_subscription(db, subscription_id, data.model_dump(exclude_unset=True))}


@router.delete('/api/admin/notification-subscriptions/{subscription_id}')
def delete_admin_notification_subscription(subscription_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
    _require_admin_session(vueio_session)
    delete_subscription(db, subscription_id)
    return {'status': 'deleted'}


@router.post('/api/admin/notification-subscriptions/{subscription_id}/test')
def test_admin_notification_subscription(subscription_id: str, vueio_session: str | None = Cookie(None), db: Session = Depends(get_db)):
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


@router.get('/api/admin/notification-deliveries')
def get_admin_notification_deliveries(
    limit: int = 100,
    vueio_session: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    _require_admin_session(vueio_session)
    deliveries = (
        db.query(NotificationDelivery)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(max(1, min(limit, 250)))
        .all()
    )
    return {'deliveries': [serialize_delivery(delivery) for delivery in deliveries]}
