"""Upload handling module."""

from app.uploads.service import ImageProcessor, process_profile_picture

__all__ = ["ImageProcessor", "process_profile_picture"]
