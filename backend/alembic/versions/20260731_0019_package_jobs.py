"""persist and authorize asynchronous package jobs

Revision ID: 20260731_0019
Revises: 20260731_0018
Create Date: 2026-07-31 13:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '20260731_0019'
down_revision = '20260731_0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'package_jobs' not in inspector.get_table_names():
        op.create_table(
            'package_jobs',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('kind', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('filename', sa.String(), nullable=False),
            sa.Column('artifact_path', sa.String(), nullable=True),
            sa.Column('total_bytes', sa.BigInteger(), nullable=False),
            sa.Column('packaged_bytes', sa.BigInteger(), nullable=False),
            sa.Column('file_count', sa.Integer(), nullable=False),
            sa.Column('packaged_files', sa.Integer(), nullable=False),
            sa.Column('progress', sa.Float(), nullable=False),
            sa.Column('message', sa.String(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('owner_type', sa.String(), nullable=False),
            sa.Column('owner_id', sa.String(), nullable=False),
            sa.Column('project_id', sa.String(), nullable=True),
            sa.Column('authorization_json', sa.Text(), nullable=True),
            sa.Column('created_at', sa.Float(), nullable=False),
            sa.Column('updated_at', sa.Float(), nullable=False),
            sa.Column('expires_at', sa.Float(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
    existing_indexes = {
        index['name']
        for index in sa.inspect(op.get_bind()).get_indexes('package_jobs')
    }
    for name, columns in (
        ('ix_package_jobs_status', ['status']),
        ('ix_package_jobs_owner_type', ['owner_type']),
        ('ix_package_jobs_owner_id', ['owner_id']),
        ('ix_package_jobs_project_id', ['project_id']),
        ('ix_package_jobs_updated_at', ['updated_at']),
        ('ix_package_jobs_expires_at', ['expires_at']),
    ):
        if name not in existing_indexes:
            op.create_index(name, 'package_jobs', columns, unique=False)


def downgrade() -> None:
    if 'package_jobs' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('package_jobs')
