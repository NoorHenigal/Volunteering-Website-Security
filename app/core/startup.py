"""Startup pre-flight checks for the application."""

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from sqlalchemy import text

from app.core.config import settings
from app.core.log import log
from app.db.session import engine

if TYPE_CHECKING:
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy.ext.asyncio import AsyncEngine
else:
    # Import alembic modules safely at runtime, avoiding conflicts with local alembic/ directory
    def _import_alembic_safely() -> tuple[type, type, type]:
        """Import alembic modules safely, avoiding conflicts with local alembic/ directory."""
        # Temporarily remove project root from sys.path to avoid import conflicts
        project_root = str(Path(__file__).parent.parent.parent)
        removed_paths = []

        # Remove project root and empty path from sys.path
        for path in sys.path[:]:
            if path in (project_root, ""):
                sys.path.remove(path)
                removed_paths.append(path)

        try:
            # ruff: noqa: PLC0415 - imports must be inside function to avoid path conflicts
            from alembic.config import Config as AlembicConfig
            from alembic.runtime.migration import MigrationContext as AlembicMigrationContext
            from alembic.script import ScriptDirectory as AlembicScriptDirectory

            return AlembicConfig, AlembicMigrationContext, AlembicScriptDirectory
        finally:
            # Restore paths
            for path in reversed(removed_paths):
                sys.path.insert(0, path)

    # Import alembic modules safely
    Config, MigrationContext, ScriptDirectory = _import_alembic_safely()

logger = logging.getLogger(__name__)


class StartupCheckError(Exception):
    """Raised when a startup check fails."""


def _log(msg: str) -> None:
    """Logs an info message."""
    log.info(msg)


def fail(msg: str) -> NoReturn:
    """Raises a startup check error.

    Args:
        msg: Error message to display

    Raises:
        StartupCheckError: Always raised with the provided message
    """
    raise StartupCheckError(msg)


async def check_database_connection(db_engine: AsyncEngine) -> None:
    """Verify that the database is accessible.

    Args:
        db_engine: SQLAlchemy async engine

    Raises:
        StartupCheckError: If database connection fails
    """
    try:
        async with db_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()
        _log("✓ Database connection established")
    except (ConnectionError, OSError) as e:
        msg = "Cannot connect to database. Please check your database is running and credentials are correct."
        raise StartupCheckError(msg) from e


async def check_migrations_applied(_db_engine: AsyncEngine) -> None:
    """Verify that all Alembic migrations have been applied.

    Args:
        db_engine: SQLAlchemy async engine

    Raises:
        StartupCheckError: If migrations are not up to date
    """
    try:
        # Load Alembic configuration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.sync_database_url.replace("%", "%%"))

        # Get script directory to find latest migration
        script = ScriptDirectory.from_config(alembic_cfg)
        head_revision = script.get_current_head()

        if head_revision is None:
            _log("✓ No migrations defined")
            return

        # Check current database revision using sync connection for Alembic
        from sqlalchemy import create_engine

        sync_engine = create_engine(settings.sync_database_url)

        with sync_engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_revision = context.get_current_revision()

        sync_engine.dispose()

        # If no migration history exists, show clear instructions
        if current_revision is None:
            fail("Database schema not initialized. Please run: uv run alembic upgrade head")

        if current_revision != head_revision:
            fail("Database schema is out of date. Please run: alembic upgrade head")

        _log("✓ Database schema up to date")

    except StartupCheckError:
        raise
    except Exception as e:
        msg = f"Failed to verify database schema: {e!s}"
        raise StartupCheckError(msg) from e


async def run_preflight_checks() -> None:
    """Runs all pre-flight checks before starting the application.

    Raises:
        StartupCheckError: If any check fails
    """
    _log("Running startup checks...")

    try:
        await check_database_connection(engine)
        await check_migrations_applied(engine)

        _log("All startup checks passed")
        _log("")

    except StartupCheckError as e:
        log.error("")
        log.error("Startup check failed")
        log.error("  Reason: %s", str(e))
        log.error("")
        log.error("Application cannot start. Please fix the issue above and try again.")
        sys.exit(1)
    except RuntimeError:
        log.exception("")
        log.exception("Unexpected startup error")
        log.exception("")
        sys.exit(1)


def exit_with_error(message: str) -> NoReturn:
    """Exit the application with an error message.

    Args:
        message: Error message to display
    """
    log.error(message)
    sys.exit(1)
