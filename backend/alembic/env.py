"""
Alembic migration environment.

Async-aware setup:
  - Uses the SYNC database URL (psycopg2) for migrations because Alembic's
    autogenerate doesn't yet support asyncpg natively.
  - Settings.sync_database_url derives the sync URL from database_url by
    swapping the asyncpg driver prefix.

Model discovery:
  - Importing ``app.models`` (the package __init__) registers every table
    in ``Base.metadata`` so autogenerate sees the full schema.
  - apply_pgvector_columns() patches Vector column types before autogenerate
    compares them against the live schema.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure the backend app is importable (alembic runs from backend/ root)
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.db import apply_pgvector_columns
from app.db.base import Base

# Register all ORM models with Base.metadata
import app.models  # noqa: F401 — side-effect import

# Patch Vector columns before autogenerate inspects metadata
apply_pgvector_columns()

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the placeholder URL from alembic.ini with the real one from Settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (no live DB connection needed).
    Alembic generates SQL scripts that can be reviewed and run manually.
    Used in CI / review workflows.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,          # detect column type changes
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (live DB connection).
    Used by ``alembic upgrade head`` in deployment pipelines.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # no connection pooling during migrations
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
