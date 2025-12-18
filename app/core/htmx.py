"""HTMX-specific response utilities."""

import contextlib
import json
from typing import TYPE_CHECKING

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from jinja2.runtime import new_context

from app.core.templates import templates

if TYPE_CHECKING:
    from app.core.context import RequestContext


def is_htmx(request: Request) -> bool:
    """Check if request is from HTMX."""
    return request.headers.get("HX-Request") == "true"


async def htmx_redirect(url: str) -> Response:
    """Return HTMX redirect response."""
    return Response(content="", headers={"HX-Redirect": url})


async def htmx_refresh() -> Response:
    """Trigger full page refresh."""
    return Response(content="", headers={"HX-Refresh": "true"})


async def handle_htmx_redirect(ctx: RequestContext, url: str) -> Response:
    """Return HTMX redirect for HTMX requests, standard redirect otherwise."""
    if ctx.is_htmx:
        return await htmx_redirect(url)
    return RedirectResponse(url=url, status_code=303)


async def render_block(request: Request, template_name: str, block_name: str, **context: object) -> Response:
    """Render a specific Jinja2 block for HTMX partial updates."""
    template = templates.get_template(template_name)

    block_func = template.blocks.get(block_name)
    if not block_func:
        msg = f"Block '{block_name}' not found in {template_name}"
        raise ValueError(msg)

    # Render full template to process imports, then extract only the requested block
    ctx = new_context(template.environment, template_name, template.blocks)
    ctx.vars.update(
        {
            "request": request,
            "csrf_token": getattr(request.state, "csrf_token", None) or request.cookies.get("csrf_token"),
            **context,
        }
    )

    with contextlib.suppress(Exception):
        list(template.root_render_func(ctx))

    html = "".join(block_func(ctx))

    return Response(content=html, media_type="text/html")


async def render_error_page(
    request: Request,
    status_code: int,
    title: str,
    message: str | None = None,
) -> Response:
    """Render a styled error page using the error template."""
    ctx = {
        "request": request,
        "page_title": title,
        "error": message,
        "csrf_token": getattr(request.state, "csrf_token", None) or request.cookies.get("csrf_token"),
    }
    return templates.TemplateResponse(request, "pages/error.html", ctx, status_code=status_code)


async def render_success_page(
    request: Request,
    title: str,
    message: str | None = None,
    details: dict[str, str] | None = None,
    redirect_url: str = "/",
    button_text: str = "Go Home",
) -> Response:
    """Render a styled success page using the success template."""
    ctx = {
        "request": request,
        "page_title": title,
        "message": message,
        "details": details,
        "redirect_url": redirect_url,
        "button_text": button_text,
        "csrf_token": getattr(request.state, "csrf_token", None) or request.cookies.get("csrf_token"),
    }
    return templates.TemplateResponse(request, "pages/success.html", ctx, status_code=200)


async def trigger_toast(response: Response, message: str, toast_type: str = "success") -> Response:
    """Add HX-Trigger header for toast notification."""
    trigger_data = {
        "show-toast": {
            "message": message,
            "type": toast_type,
        }
    }

    current_header = response.headers.get("HX-Trigger")
    if current_header:
        try:
            existing = json.loads(current_header)
            if isinstance(existing, str):
                existing = {existing: True}
            elif not isinstance(existing, dict):
                existing = {}
        except json.JSONDecodeError:
            existing = {current_header: True}

        existing.update(trigger_data)
        response.headers["HX-Trigger"] = json.dumps(existing)
    else:
        response.headers["HX-Trigger"] = json.dumps(trigger_data)

    return response
