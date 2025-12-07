"""HTMX-specific response utilities."""

import contextlib
import json

from fastapi import Request, Response
from jinja2.runtime import new_context

from app.core.templates import templates


def is_htmx(request: Request) -> bool:
    """Check if request is from HTMX."""
    return request.headers.get("HX-Request") == "true"


def htmx_redirect(url: str) -> Response:
    """Return HTMX redirect response."""
    return Response(content="", headers={"HX-Redirect": url})


def htmx_refresh() -> Response:
    """Trigger full page refresh."""
    return Response(content="", headers={"HX-Refresh": "true"})


def render_block(request: Request, template_name: str, block_name: str, **context: object) -> Response:
    """Render a specific block from a template (for HTMX responses).

    This is the SECRET SAUCE - render just one block without creating
    separate fragment files!

    The solution: We need to let Jinja2 process the entire template (which handles
    imports), but we intercept and only return the specific block's content.
    """
    template = templates.get_template(template_name)

    # Get the specific block
    block_func = template.blocks.get(block_name)
    if not block_func:
        msg = f"Block '{block_name}' not found in {template_name}"
        raise ValueError(msg)

    # The key: render the full template to process imports, but capture only the block
    # We do this by creating a context and calling root_render_func which processes
    # all imports, then we extract just our block from that context
    ctx = new_context(template.environment, template_name, template.blocks)
    ctx.vars.update({"request": request, **context})

    # Call the template's root render function to process imports
    # This populates the context with all imported macros
    with contextlib.suppress(Exception):
        # If root render fails, continue - imports should still be in context
        list(template.root_render_func(ctx))

    # Now render just the block we want with the fully-initialized context
    html = "".join(block_func(ctx))

    return Response(content=html, media_type="text/html")


def trigger_toast(response: Response, message: str, toast_type: str = "success") -> Response:
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
            # Header was 'event-name' (not valid JSON)
            existing = {current_header: True}

        existing.update(trigger_data)
        response.headers["HX-Trigger"] = json.dumps(existing)
    else:
        response.headers["HX-Trigger"] = json.dumps(trigger_data)

    return response
