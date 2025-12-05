"""Jinja2 templates configuration."""

from pathlib import Path

from starlette.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["zip"] = zip
