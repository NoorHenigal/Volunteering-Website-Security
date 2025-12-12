"""Main FastAPI application."""

import logging
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.context import ContextDep, render_template
from app.core.exceptions import http_exception_handler, validation_exception_handler
from app.core.lifecycle import StartupCheckError, cleanup_shutdown_task, manage_test_shutdown, run_preflight_checks
from app.opportunities.router import router as opp_router
from app.organizations.router import router as org_router
from app.profiles.router import router as profiles_router

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
        await run_preflight_checks()
    except StartupCheckError as e:
        sys.stderr.write(f"Startup check failed: {e}\n")
        sys.stderr.flush()
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

# Register global exception handlers for consistent error responses
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


log = logging.getLogger(__name__)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions - log but don't leak stack traces."""
    log.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "status_code": 500, "error_code": None},
    )


# Mount static files
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", include_in_schema=False)
async def home(ctx: ContextDep) -> Response:
    """Home page."""
    return await render_template(ctx.request, "pages/home.html", user=ctx.user)


app.include_router(auth_router)
app.include_router(opp_router)
app.include_router(org_router)
app.include_router(profiles_router)
