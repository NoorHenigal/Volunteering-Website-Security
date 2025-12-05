"""UI Development mode FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from app.core.lifecycle import cleanup_shutdown_task, manage_test_shutdown

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi.responses import Response


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler.

    Args:
        _app: FastAPI application instance

    Yields:
        None
    """
    # If TEST_RUN_DURATION is set, schedule automatic shutdown
    shutdown_task = await manage_test_shutdown()

    yield

    # Shutdown: Cancel auto-shutdown task if it's still running
    await cleanup_shutdown_task(shutdown_task)


# Create FastAPI app for UI development
app = FastAPI(
    title="Volunteering Web App - UI Dev Mode",
    description="UI Development Mode (No Database Required)",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Setup templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/")
async def home(request: Request) -> Response:
    """Home page with mock data.

    Args:
        request: FastAPI request object

    Returns:
        Rendered home page template
    """
    # Mock user data for UI development
    mock_user = None  # Not logged in by default
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request, "user": mock_user},
    )


@app.get("/auth/login")
async def login_form(request: Request) -> Response:
    """Login form page.

    Args:
        request: FastAPI request object

    Returns:
        Rendered login template
    """
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "user": None},
    )


@app.get("/auth/register")
async def register_form(request: Request) -> Response:
    """Registration form page.

    Args:
        request: FastAPI request object

    Returns:
        Rendered registration template
    """
    return templates.TemplateResponse(
        request,
        "register.html",
        {"request": request, "user": None},
    )


@app.get("/auth/status")
async def status_page(request: Request) -> Response:
    """Status page with mock logged-in user.

    Args:
        request: FastAPI request object

    Returns:
        Rendered status template
    """
    # Mock logged-in user for UI development
    mock_user = {
        "id": 1,
        "email": "dev@example.com",
        "role": "volunteer",
    }
    return templates.TemplateResponse(
        request,
        "status.html",
        {"request": request, "user": mock_user},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy", "mode": "ui-dev"}
