"""Jinja2 templates configuration."""

from pathlib import Path

from starlette.templating import Jinja2Templates

from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["zip"] = zip
templates.env.globals["settings"] = settings
