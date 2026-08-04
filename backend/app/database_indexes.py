from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection


INDEX_CONVERGENCE_REVISION = '20260713_0011'


@lru_cache(maxsize=1)
def index_convergence_module():
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / 'alembic.ini'))
    config.set_main_option('script_location', str(backend_dir / 'alembic'))
    return ScriptDirectory.from_config(config).get_revision(INDEX_CONVERGENCE_REVISION).module


def canonical_index_specs():
    return index_convergence_module().CANONICAL_INDEXES


def verify_database_indexes(conn: Connection) -> None:
    migration = index_convergence_module()
    missing = []
    for spec in migration.CANONICAL_INDEXES:
        index_name, table_name, _columns, _unique, _predicate = spec
        actual = migration._indexes(conn, table_name).get(index_name)
        if actual is None or not migration._matches(actual, spec):
            missing.append(f'{table_name}.{index_name}')
    if missing:
        raise RuntimeError(f'Database index contract is incomplete: {", ".join(sorted(missing))}')
