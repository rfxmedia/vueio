from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session

from app.models import HorizonProject, RecentlyViewed
from app.services.horizons_fresh import DELETED_PROJECT_STATUS

PROJECT_RECENT_ITEM_TYPES = ('project', 'horizon_project')


def _recently_viewed_matches_project(project_id):
    return or_(
        RecentlyViewed.project_id == project_id,
        and_(
            RecentlyViewed.item_type.in_(PROJECT_RECENT_ITEM_TYPES),
            RecentlyViewed.item_id == project_id,
        ),
    )


def exclude_deleted_project_recently_viewed(query: Query, db: Session) -> Query:
    deleted_project_exists = (
        db.query(HorizonProject.id)
        .filter(HorizonProject.status == DELETED_PROJECT_STATUS)
        .filter(_recently_viewed_matches_project(HorizonProject.id))
        .exists()
    )
    return query.filter(~deleted_project_exists)


def purge_recently_viewed_for_project(db: Session, project_id: str) -> int:
    return (
        db.query(RecentlyViewed)
        .filter(_recently_viewed_matches_project(project_id))
        .delete(synchronize_session=False)
    )
