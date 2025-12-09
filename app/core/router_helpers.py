"""Router helper functions."""

from fastapi import Response
from fastapi.responses import RedirectResponse

from app.core.context import ContextDep
from app.core.htmx import htmx_redirect


async def handle_htmx_redirect(ctx: ContextDep, url: str) -> Response:
    """Return HTMX redirect for HTMX requests, standard redirect otherwise."""
    if ctx.is_htmx:
        return await htmx_redirect(url)
    return RedirectResponse(url=url, status_code=303)
