"""Startup checks and application lifecycle."""

import asyncio
import logging
import os
import signal
from contextlib import suppress

import psutil
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal, sync_engine

log = logging.getLogger(__name__)


ARGON2_PROFILE_INCOMPATIBLE_MSG = (
    "Host machine does not meet requirements for configured Argon2 profile "
    "(ARGON2_PROFILE=RFC_9106_HIGH_MEMORY). Choose RFC_9106_LOW_MEMORY or see Argon2-Info.md."
)


class StartupCheckError(Exception):
    """Raised when a startup check fails."""


def _check_argon2_profile_compatibility() -> None:
    if settings.argon2_profile != "RFC_9106_HIGH_MEMORY":
        return

    total_ram_bytes = int(psutil.virtual_memory().total)
    total_ram_gib = total_ram_bytes / (1024**3)
    cpu_cores = os.cpu_count() or 1

    min_ram_gib = 6
    min_cpu_cores = 2

    if total_ram_gib < min_ram_gib or cpu_cores < min_cpu_cores:
        msg = ARGON2_PROFILE_INCOMPATIBLE_MSG
        raise StartupCheckError(msg)


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


async def _ensure_admin_account() -> None:
    """Create initial admin account if enabled and none exists."""
    if not settings.create_admin_on_launch:
        return

    from app.admin.setup import create_initial_admin  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        result = await create_initial_admin(db)
        if result:
            email, password = result
            log.warning("=" * 60)
            log.warning("INITIAL ADMIN ACCOUNT CREATED")
            log.warning("Email: %s", email)
            log.warning("Password: %s", password)
            log.warning("You MUST change these credentials on first login!")
            log.warning("=" * 60)
        else:
            log.info("✓ Admin account exists")


async def run_preflight_checks() -> None:
    """Run all pre-flight checks before starting the application."""
    if os.getenv("SKIP_PREFLIGHT_CHECKS") == "1":
        return

    log.info("Running startup checks...")

    _check_argon2_profile_compatibility()
    _check_database_connection()
    _check_migrations()
    await _ensure_admin_account()

    log.info("All startup checks passed\n")


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
