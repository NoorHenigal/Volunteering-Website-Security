"""Router helper functions to eliminate code duplication across router files."""

from fastapi import Response
from fastapi.responses import RedirectResponse

from app.core.context import ContextDep
from app.core.htmx import htmx_redirect


def handle_htmx_redirect(ctx: ContextDep, url: str) -> Response:
    """Handle HTMX-aware redirects.

    Returns HTMX redirect for HTMX requests, otherwise returns standard RedirectResponse.
    This consolidates the repeated pattern across all router files.
    """
    if ctx.is_htmx:
        return htmx_redirect(url)
    return RedirectResponse(url=url, status_code=303)
