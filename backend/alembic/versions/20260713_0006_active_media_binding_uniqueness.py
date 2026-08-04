"""enforce one active media generation per path binding

Revision ID: 20260713_0006
Revises: 20260713_0005
Create Date: 2026-07-13 15:30:00
"""

from alembic import op
import sqlalchemy as sa
import time

revision = '20260713_0006'
down_revision = '20260713_0005'
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    if table_name not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def _reference_score_sql(bind, alias: str = 'media_assets') -> str:
    table_columns = {
        table_name: _columns(bind, table_name)
        for table_name in (
            'shares',
            'horizons_shots',
            'horizons_shot_versions',
            'comments',
            'shot_registry',
            'version_registry',
            'media_metadata',
        )
    }
    score_parts = []
    if 'media_asset_id' in table_columns['shares']:
        active_filter = " AND COALESCE(shares.is_active, true) = true" if 'is_active' in table_columns['shares'] else ''
        score_parts.append(f"(SELECT COUNT(*) * 100 FROM shares WHERE shares.media_asset_id = {alias}.id{active_filter})")
    if 'latest_media_asset_id' in table_columns['horizons_shots']:
        score_parts.append(f"(SELECT COUNT(*) * 80 FROM horizons_shots WHERE horizons_shots.latest_media_asset_id = {alias}.id)")
    if 'media_asset_id' in table_columns['horizons_shot_versions']:
        score_parts.append(f"(SELECT COUNT(*) * 60 FROM horizons_shot_versions WHERE horizons_shot_versions.media_asset_id = {alias}.id)")
    if 'horizons_media_asset_id' in table_columns['comments']:
        score_parts.append(f"(SELECT COUNT(*) * 20 FROM comments WHERE comments.horizons_media_asset_id = {alias}.id)")
    if 'latest_media_asset_id' in table_columns['shot_registry']:
        score_parts.append(f"(SELECT COUNT(*) * 20 FROM shot_registry WHERE shot_registry.latest_media_asset_id = {alias}.id)")
    if 'media_asset_id' in table_columns['version_registry']:
        score_parts.append(f"(SELECT COUNT(*) * 20 FROM version_registry WHERE version_registry.media_asset_id = {alias}.id)")
    if 'media_asset_id' in table_columns['media_metadata']:
        score_parts.append(f"(SELECT COUNT(*) FROM media_metadata WHERE media_metadata.media_asset_id = {alias}.id)")
    return ' + '.join(score_parts) if score_parts else '0'


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if 'media_assets' not in tables:
        return

    now = time.time()
    reference_score_sql = _reference_score_sql(bind)
    if 'media_asset_duplicate_retire_audit' not in tables:
        op.create_table(
            'media_asset_duplicate_retire_audit',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('migration_revision', sa.String(), nullable=False),
            sa.Column('media_asset_id', sa.String(), nullable=False),
            sa.Column('previous_unavailable_at', sa.Float(), nullable=True),
            sa.Column('previous_unavailable_reason', sa.String(), nullable=True),
            sa.Column('previous_updated_at', sa.Float(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=False),
        )
    op.execute(sa.text("""
        INSERT INTO media_asset_duplicate_retire_audit (
            migration_revision,
            media_asset_id,
            previous_unavailable_at,
            previous_unavailable_reason,
            previous_updated_at,
            created_at
        )
        SELECT
            :revision,
            id,
            unavailable_at,
            unavailable_reason,
            updated_at,
            :now
        FROM (
          SELECT
            id,
            unavailable_at,
            unavailable_reason,
            updated_at,
            ROW_NUMBER() OVER (
              PARTITION BY project_id, storage_scope, file_path
              ORDER BY
                (""" + reference_score_sql + """) DESC,
                CASE WHEN source_signature IS NULL OR source_signature = '' THEN 0 ELSE 1 END DESC,
                COALESCE(updated_at, 0) DESC,
                COALESCE(created_at, 0) DESC,
                id ASC
            ) AS binding_rank
          FROM media_assets
          WHERE unavailable_at IS NULL
        ) ranked_media_assets
        WHERE binding_rank > 1
    """).bindparams(revision=revision, now=now))
    op.execute(sa.text("""
        UPDATE media_assets
        SET unavailable_at = CASE WHEN unavailable_at IS NULL THEN :now ELSE unavailable_at END,
            unavailable_reason = COALESCE(unavailable_reason, 'duplicate_active_generation'),
            updated_at = CASE WHEN updated_at IS NULL OR updated_at < :now THEN :now ELSE updated_at END
        WHERE unavailable_at IS NULL
          AND id IN (
            SELECT id
            FROM (
              SELECT
                id,
                ROW_NUMBER() OVER (
                  PARTITION BY project_id, storage_scope, file_path
                  ORDER BY
                    (""" + reference_score_sql + """) DESC,
                    CASE WHEN source_signature IS NULL OR source_signature = '' THEN 0 ELSE 1 END DESC,
                    COALESCE(updated_at, 0) DESC,
                    COALESCE(created_at, 0) DESC,
                    id ASC
                ) AS binding_rank
              FROM media_assets
              WHERE unavailable_at IS NULL
            ) ranked_media_assets
            WHERE binding_rank > 1
          )
    """).bindparams(now=now))
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_media_assets_active_owner_scope_path
        ON media_assets (project_id, storage_scope, file_path)
        WHERE unavailable_at IS NULL
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if 'media_asset_duplicate_retire_audit' not in set(sa.inspect(bind).get_table_names()):
        raise RuntimeError('Cannot restore duplicate media asset state: migration audit table is missing')
    op.execute('DROP INDEX IF EXISTS uq_media_assets_active_owner_scope_path')
    op.execute(sa.text("""
        UPDATE media_assets
        SET unavailable_at = (
                SELECT previous_unavailable_at
                FROM media_asset_duplicate_retire_audit
                WHERE media_asset_duplicate_retire_audit.media_asset_id = media_assets.id
                  AND media_asset_duplicate_retire_audit.migration_revision = :revision
                ORDER BY media_asset_duplicate_retire_audit.id DESC
                LIMIT 1
            ),
            unavailable_reason = (
                SELECT previous_unavailable_reason
                FROM media_asset_duplicate_retire_audit
                WHERE media_asset_duplicate_retire_audit.media_asset_id = media_assets.id
                  AND media_asset_duplicate_retire_audit.migration_revision = :revision
                ORDER BY media_asset_duplicate_retire_audit.id DESC
                LIMIT 1
            ),
            updated_at = (
                SELECT previous_updated_at
                FROM media_asset_duplicate_retire_audit
                WHERE media_asset_duplicate_retire_audit.media_asset_id = media_assets.id
                  AND media_asset_duplicate_retire_audit.migration_revision = :revision
                ORDER BY media_asset_duplicate_retire_audit.id DESC
                LIMIT 1
            )
        WHERE unavailable_reason = 'duplicate_active_generation'
          AND id IN (
            SELECT media_asset_id
            FROM media_asset_duplicate_retire_audit
            WHERE migration_revision = :revision
          )
    """).bindparams(revision=revision))
