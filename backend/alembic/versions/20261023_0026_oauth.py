"""store Sign in with Vue.io clients, connected apps and tokens

Revision ID: 20261023_0026
Revises: 20261019_0025
Create Date: 2026-10-23 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = '20261023_0026'
down_revision = '20261019_0025'
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if 'oauth_clients' not in tables:
        op.create_table(
            'oauth_clients',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('redirect_uris_json', sa.Text(), nullable=False),
            sa.Column('source', sa.String(), nullable=False),
            sa.Column('metadata_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=True),
            sa.Column('updated_at', sa.Float(), nullable=True),
        )
    if 'oauth_grants' not in tables:
        op.create_table(
            'oauth_grants',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('client_id', sa.String(), nullable=False),
            sa.Column('client_name', sa.String(), nullable=False),
            sa.Column('resource', sa.String(), nullable=False),
            sa.Column('created_at', sa.Float(), nullable=True),
            sa.Column('last_used_at', sa.Float(), nullable=True),
            sa.Column('revoked_at', sa.Float(), nullable=True),
        )
        op.create_index('idx_oauth_grants_user_id', 'oauth_grants', ['user_id'])
        op.create_index('idx_oauth_grants_client_id', 'oauth_grants', ['client_id'])
    if 'oauth_tokens' not in tables:
        op.create_table(
            'oauth_tokens',
            sa.Column('token_hash', sa.String(), primary_key=True),
            sa.Column('grant_id', sa.String(), nullable=False),
            sa.Column('kind', sa.String(), nullable=False),
            sa.Column('expires_at', sa.Float(), nullable=False),
            sa.Column('used_at', sa.Float(), nullable=True),
            sa.Column('data_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=True),
        )
        op.create_index('idx_oauth_tokens_grant_id', 'oauth_tokens', ['grant_id'])
        op.create_index('idx_oauth_tokens_expires_at', 'oauth_tokens', ['expires_at'])


def downgrade() -> None:
    tables = _tables()
    for table in ('oauth_tokens', 'oauth_grants', 'oauth_clients'):
        if table in tables:
            op.drop_table(table)
