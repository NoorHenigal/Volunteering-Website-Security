"""Application lifecycle management: startup checks and lifespan utilities."""

import asyncio
import logging
import os
import signal
from contextlib import suppress

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import settings
from app.db.seed import seed_demo_data
from app.db.session import sync_engine

log = logging.getLogger(__name__)


class StartupCheckError(Exception):
    """Raised when a startup check fails."""


def _check_database_connection() -> None:
    """Verify database accessibility."""
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("✓ Database connection established")
    except Exception as e:
        msg = "Cannot connect to database. Check that it's running and credentials are correct."
        raise StartupCheckError(msg) from e


def _check_migrations() -> None:
    """Verify all Alembic migrations are applied."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

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


async def run_preflight_checks() -> None:
    """Run all pre-flight checks before starting the application.

    This function is async to support demo data seeding.
    """
    log.info("Running startup checks...")

    try:
        _check_database_connection()
        _check_migrations()

        # Seed demo data if enabled
        if settings.demo_data:
            log.info("DEMO_DATA enabled, checking demo data...")
            await seed_demo_data()

        log.info("All startup checks passed\n")

    except StartupCheckError:
        log.exception("Startup check failed")
        log.warning("Application cannot start. Fix the issue above and try again.\n")
        raise


async def auto_shutdown(duration: int) -> None:
    """Automatically shutdown the application after specified duration."""
    log.warning("TEST MODE: Server will shutdown in %d seconds", duration)
    await asyncio.sleep(duration)
    log.warning("TEST MODE: %d seconds elapsed, shutting down gracefully", duration)
    os.kill(os.getppid(), signal.SIGTERM)


async def manage_test_shutdown() -> asyncio.Task[None] | None:
    """Start auto-shutdown task if TEST_RUN_DURATION is set."""
    if test_duration := os.getenv("TEST_RUN_DURATION"):
        return asyncio.create_task(auto_shutdown(int(test_duration)))
    return None


async def cleanup_shutdown_task(shutdown_task: asyncio.Task[None] | None) -> None:
    """Cancel and cleanup a shutdown task if it's still running."""
    if shutdown_task and not shutdown_task.done():
        shutdown_task.cancel()
        with suppress(asyncio.CancelledError):
            await shutdown_task


__all__ = [
    "StartupCheckError",
    "cleanup_shutdown_task",
    "manage_test_shutdown",
    "run_preflight_checks",
]
