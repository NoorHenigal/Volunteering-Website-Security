"""Startup pre-flight checks for the application."""

import logging

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import settings
from app.db.session import sync_engine

log = logging.getLogger(__name__)


class StartupCheckError(Exception):
    """Raised when a startup check fails."""


def _check_database_connection() -> None:
    """Verify database accessibility.

    Raises:
        StartupCheckError: If database connection fails
    """
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("✓ Database connection established")
    except Exception as e:
        msg = "Cannot connect to database. Check that it's running and credentials are correct."
        raise StartupCheckError(msg) from e


def _check_migrations() -> None:
    """Verify all Alembic migrations are applied.

    Raises:
        StartupCheckError: If migrations are not up to date
    """
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.sync_database_url.replace("%", "%%"))

    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()

    if not head:
        log.info("✓ No migrations defined")
        return

    with sync_engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()

    if not current:
        msg = "Database schema not initialized. Run: uv run alembic upgrade head"
        raise StartupCheckError(msg)

    if current != head:
        msg = "Database schema out of date. Run: alembic upgrade head"
        raise StartupCheckError(msg)

    log.info("✓ Database schema up to date")


def run_preflight_checks() -> None:
    """Run all pre-flight checks before starting the application.

    Raises:
        StartupCheckError: If any check fails
    """
    log.info("Running startup checks...")

    try:
        _check_database_connection()
        _check_migrations()
        log.info("All startup checks passed\n")

    except StartupCheckError as e:
        log.error("\nStartup check failed: %s\n", e)
        log.error("Application cannot start. Fix the issue above and try again.\n")
        raise
