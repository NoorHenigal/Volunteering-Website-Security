"""Alembic migration environment."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, pool

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

from alembic import context

from app.core.config import settings
from app.db.models import Base

# Configure logging
logger = logging.getLogger("alembic")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(levelname)-5.5s [%(name)s] %(message)s"))
logger.addHandler(handler)

# Alembic configuration
config = context.config

# Apply sync database URL to alembic.ini
db_url = settings.sync_database_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", db_url)

logger.info("Starting Alembic migrations")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    logger.info("Running migrations offline")

    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations synchronously."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    logger.info("Running migrations online")

    connectable = create_engine(
        db_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
