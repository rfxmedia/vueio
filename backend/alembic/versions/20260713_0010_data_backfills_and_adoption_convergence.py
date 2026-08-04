"""converge deterministic data backfills

Revision ID: 20260713_0010
Revises: 20260713_0009
Create Date: 2026-07-13 21:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260713_0010'
down_revision = '20260713_0009'
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table_name: str) -> set[str]:
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def _tracker_matches(bind, project_id: str, tracker_name: str) -> list[str]:
    return bind.execute(
        sa.text("""
            SELECT id
            FROM horizons_trackers
            WHERE project_id = :project_id
              AND (id = :tracker_name OR slug = :tracker_name OR name = :tracker_name)
            ORDER BY id
        """),
        {'project_id': project_id, 'tracker_name': tracker_name},
    ).scalars().all()


def _planned_tracker_updates(bind, table_name: str) -> list[tuple[str, str]]:
    columns = _columns(bind, table_name)
    if not {'project_id', 'tracker_id', 'tracker_name'}.issubset(columns):
        return []
    share_filter = "AND share_type = 'tracker'" if table_name == 'shares' and 'share_type' in columns else ''
    rows = bind.execute(sa.text(f"""
        SELECT id, project_id, tracker_id, tracker_name
        FROM {table_name}
        WHERE project_id IS NOT NULL
          AND tracker_name IS NOT NULL
          AND TRIM(tracker_name) != ''
          {share_filter}
    """)).mappings().all()
    updates: list[tuple[str, str]] = []
    for row in rows:
        matches = _tracker_matches(bind, row['project_id'], row['tracker_name'])
        if not matches:
            continue
        if len(matches) > 1:
            raise RuntimeError(f'Ambiguous tracker match on {table_name}.{row["id"]}')
        match = matches[0]
        if row['tracker_id'] is not None:
            if row['tracker_id'] != match:
                raise RuntimeError(f'Conflicting tracker_id on {table_name}.{row["id"]}')
            continue
        updates.append((row['id'], match))
    return updates


def _apply_tracker_updates(bind, table_name: str, updates: list[tuple[str, str]]) -> None:
    for row_id, tracker_id in updates:
        bind.execute(
            sa.text(f'UPDATE {table_name} SET tracker_id = :tracker_id WHERE id = :id'),
            {'tracker_id': tracker_id, 'id': row_id},
        )


def _plan_tracker_identity_refs(bind) -> dict[str, list[tuple[str, str]]]:
    if 'horizons_trackers' not in _tables(bind):
        return {}
    plan: dict[str, list[tuple[str, str]]] = {}
    for table_name in ('shares', 'version_registry', 'shot_registry'):
        if table_name in _tables(bind):
            plan[table_name] = _planned_tracker_updates(bind, table_name)
    return plan


def _plan_horizon_shot_assignees(bind) -> list[dict[str, object]]:
    if not {'horizons_shots', 'horizons_shot_assignees'}.issubset(_tables(bind)):
        return []
    rows = bind.execute(sa.text("""
        SELECT id, project_id, tracker_id, assignee_user_id, updated_at, created_at
        FROM horizons_shots
        WHERE assignee_user_id IS NOT NULL AND TRIM(assignee_user_id) != ''
    """)).mappings().all()
    inserts: list[dict[str, object]] = []
    for row in rows:
        existing_pair = bind.execute(
            sa.text("""
                SELECT id, project_id, tracker_id
                FROM horizons_shot_assignees
                WHERE shot_id = :shot_id AND user_id = :user_id
                LIMIT 1
            """),
            {'shot_id': row['id'], 'user_id': row['assignee_user_id']},
        ).mappings().first()
        if existing_pair:
            if existing_pair['project_id'] != row['project_id'] or existing_pair['tracker_id'] != row['tracker_id']:
                raise RuntimeError(f'Incompatible existing assignee pair for {row["id"]}:{row["assignee_user_id"]}')
            continue
        assignee_id = f"{row['id']}:{row['assignee_user_id']}"
        existing_id = bind.execute(
            sa.text('SELECT shot_id, user_id FROM horizons_shot_assignees WHERE id = :id'),
            {'id': assignee_id},
        ).mappings().first()
        if existing_id is not None:
            raise RuntimeError(f'Generated assignee id collision for {assignee_id}')
        timestamp = row['updated_at'] if row['updated_at'] is not None else row['created_at']
        if timestamp is None:
            timestamp = 0.0
        inserts.append({
            'id': assignee_id,
            'project_id': row['project_id'],
            'tracker_id': row['tracker_id'],
            'shot_id': row['id'],
            'user_id': row['assignee_user_id'],
            'created_at': timestamp,
            'updated_at': timestamp,
        })
    return inserts


def _apply_assignee_inserts(bind, inserts: list[dict[str, object]]) -> None:
    for values in inserts:
        bind.execute(
            sa.text("""
                INSERT INTO horizons_shot_assignees (
                    id, project_id, tracker_id, shot_id, user_id, sort_order,
                    created_by, created_at, updated_at
                ) VALUES (
                    :id, :project_id, :tracker_id, :shot_id, :user_id, 0,
                    NULL, :created_at, :updated_at
                )
            """),
            values,
        )


def upgrade() -> None:
    bind = op.get_bind()
    tracker_plan = _plan_tracker_identity_refs(bind)
    assignee_inserts = _plan_horizon_shot_assignees(bind)
    for table_name, updates in tracker_plan.items():
        _apply_tracker_updates(bind, table_name, updates)
    _apply_assignee_inserts(bind, assignee_inserts)


def downgrade() -> None:
    # Data-preserving downgrade: these backfills are deterministic adoption
    # convergence and must not delete exact IDs/timestamps on rollback.
    return
