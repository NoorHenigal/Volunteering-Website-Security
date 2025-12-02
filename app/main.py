"""Main FastAPI application."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.auth.router import api_router as auth_api_router
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.context import ContextDep, render_template
from app.core.lifecycle import StartupCheckError, cleanup_shutdown_task, manage_test_shutdown, run_preflight_checks
from app.opportunities.router import api_router as opp_api_router
from app.opportunities.router import app_api_router
from app.opportunities.router import ui_router as opp_ui_router
from app.organizations.router import api_router as org_api_router
from app.organizations.router import ui_router as org_ui_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler.

    Runs pre-flight checks on startup and cleanup on shutdown.

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup: Run pre-flight checks
    try:
        run_preflight_checks()
    except StartupCheckError:
        # Error already logged, exit immediately without traceback
        os._exit(1)

    # If TEST_RUN_DURATION is set, schedule automatic shutdown
    shutdown_task = await manage_test_shutdown()

    yield

    # Shutdown: Cancel auto-shutdown task if it's still running
    await cleanup_shutdown_task(shutdown_task)


# Create FastAPI app
app = FastAPI(
    title="Volunteering Web App",
    description="KV6014",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Include routers
app.include_router(auth_router)
app.include_router(auth_api_router)
app.include_router(opp_api_router)
app.include_router(app_api_router)
app.include_router(opp_ui_router)
app.include_router(org_api_router)
app.include_router(org_ui_router)


@app.get("/")
async def home(ctx: ContextDep) -> Response:
    """Home page."""
    return render_template(ctx.request, "index.html", user=ctx.user)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy"}
