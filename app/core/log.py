"""Minimal global logger for the app."""

import logging

from app.core.config import settings

# Get log level from config, default to "normal"
log_level_env = settings.log_level
LEVEL = logging.DEBUG if log_level_env == "debug" else logging.WARNING

# Configure logging
logging.basicConfig(level=LEVEL, format="[%(levelname)s] %(message)s", force=True)

# Single app logger
log = logging.getLogger("app")
