from __future__ import annotations

import errno
import fcntl
import time
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

from .database_indexes import verify_database_indexes
from .models import Base


POSTGRES_MIGRATION_LOCK_KEY = 84_783_001
MIGRATION_LOCK_TIMEOUT_SECONDS = 60
POSTGRES_STATEMENT_TIMEOUT = '10min'
SQLITE_LEGACY_ADOPTION_REVISION = '20260712_0004'
SQLITE_ADOPTION_PREFLIGHT_REVISION = '20260713_0009'


def alembic_config(connection: Connection | None = None) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / 'alembic.ini'))
    config.set_main_option('script_location', str(backend_dir / 'alembic'))
    if connection is not None:
        config.attributes['connection'] = connection
    return config


def alembic_head() -> str:
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f'Expected one Alembic head, found {heads!r}')
    return heads[0]


def run_alembic_upgrade(connection: Connection) -> None:
    command.upgrade(alembic_config(connection), 'head')


def adopt_existing_sqlite_schema(connection: Connection) -> None:
    """Adopt the rehearsed legacy SQLite shape before Alembic owns upgrades."""
    inspector = inspect(connection)
    if inspector.has_table('alembic_version'):
        current = connection.execute(text('SELECT version_num FROM alembic_version LIMIT 1')).scalar()
        if current:
            return
    app_tables = set(inspector.get_table_names()).intersection(Base.metadata.tables)
    if not app_tables:
        return

    script = ScriptDirectory.from_config(alembic_config())
    preflight = script.get_revision(SQLITE_ADOPTION_PREFLIGHT_REVISION).module
    evidence = preflight._stale_share_value_plan(connection)
    preflight._preflight(connection, evidence)
    command.stamp(alembic_config(connection), SQLITE_LEGACY_ADOPTION_REVISION)


def verify_alembic_head(connection: Connection) -> None:
    inspector = inspect(connection)
    if not inspector.has_table('alembic_version'):
        raise RuntimeError('Database is missing alembic_version after migration')
    revisions = connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
    expected = alembic_head()
    if revisions != [expected]:
        raise RuntimeError(f'Database revision mismatch: expected {expected}, found {revisions!r}')


def verify_schema_contract(connection: Connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    failures = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            failures.append(f'missing table {table.name}')
            continue
        expected = set(table.columns.keys())
        actual = {column['name'] for column in inspector.get_columns(table.name)}
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            failures.append(f'{table.name} columns missing={missing!r} extra={extra!r}')
    if failures:
        raise RuntimeError(f'Database schema contract is incomplete: {"; ".join(failures)}')
    verify_database_indexes(connection)


def _sqlite_lock_path(engine: Engine) -> Path:
    database = engine.url.database
    if not database or database == ':memory:':
        return Path.cwd() / '.vueio-migrate.lock'
    return Path(database).resolve().parent / '.vueio-migrate.lock'


@contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as lock_file:
        deadline = time.monotonic() + MIGRATION_LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN) or time.monotonic() >= deadline:
                    raise RuntimeError(f'Timed out acquiring SQLite migration lock {path}') from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def migration_connection(engine: Engine):
    if engine.dialect.name == 'sqlite':
        with _file_lock(_sqlite_lock_path(engine)), engine.connect() as connection:
            connection.exec_driver_sql(f'PRAGMA busy_timeout = {MIGRATION_LOCK_TIMEOUT_SECONDS * 1000}')
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return
    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL lock_timeout = '{MIGRATION_LOCK_TIMEOUT_SECONDS}s'"))
        connection.execute(text(f"SET LOCAL statement_timeout = '{POSTGRES_STATEMENT_TIMEOUT}'"))
        connection.execute(
            text('SELECT pg_advisory_xact_lock(:lock_key)'),
            {'lock_key': POSTGRES_MIGRATION_LOCK_KEY},
        )
        yield connection
