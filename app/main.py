"""Main FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.templating import Jinja2Templates

from app.auth.router import api_router as auth_api_router
from app.auth.router import ui_router as auth_ui_router
from app.core.config import settings
from app.core.security import get_user_from_cookie
from app.core.startup import run_preflight_checks
from app.db.session import get_db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi.responses import Response
    from sqlalchemy.ext.asyncio import AsyncSession


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
    await run_preflight_checks()
    yield
    # Shutdown: Add cleanup logic here if needed


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

# Setup templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Include routers
app.include_router(auth_api_router)
app.include_router(auth_ui_router)


@app.get("/")
async def home(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Home page.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        Rendered home page template
    """
    user = await get_user_from_cookie(request, db)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request, "user": user},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy"}
