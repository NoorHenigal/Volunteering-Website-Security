"""Exception handlers and error helpers."""

from __future__ import annotations

import json
from collections.abc import Sequence

from fastapi import HTTPException, Request, status
from starlette.responses import RedirectResponse, Response
from starlette.routing import Match

from app.core.htmx import render_error_page

HTTP_303_SEE_OTHER = 303

HTTP_405_METHOD_NOT_ALLOWED = 405


def serialize_validation_errors(errors: Sequence[object]) -> list[object]:
    """Convert validation errors to JSON-serializable format."""
    return json.loads(json.dumps(list(errors), default=str))  # type: ignore[no-any-return]


def require[T](entity: T | None, message: str, code: int = status.HTTP_404_NOT_FOUND) -> T:
    """Return entity or raise HTTPException if None."""
    if entity is None:
        raise HTTPException(status_code=code, detail=message)
    return entity


def forbid(condition: bool, message: str) -> None:
    """Raise 403 if condition is True."""
    if condition:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def conflict(condition: bool, message: str) -> None:
    """Raise 409 if condition is True."""
    if condition:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle HTTP exceptions. Returns HTML error page for UI requests."""
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc))
    headers: dict[str, str] = getattr(exc, "headers", None) or {}

    if status_code == HTTP_303_SEE_OTHER and "Location" in headers:
        return RedirectResponse(url=headers["Location"], status_code=HTTP_303_SEE_OTHER)

    if status_code == HTTP_405_METHOD_NOT_ALLOWED:
        allowed: set[str] = set()
        for route in request.app.routes:
            match, _ = route.matches({"type": "http", "path": request.url.path, "method": "GET"})
            if match in (Match.PARTIAL, Match.FULL) and hasattr(route, "methods"):
                allowed.update(route.methods)
        if allowed:
            if "GET" in allowed:
                allowed.add("HEAD")
            allowed.add("OPTIONS")
            headers["Allow"] = ", ".join(sorted(allowed))

    response = await render_error_page(request, status_code, f"Error {status_code}", detail)
    for key, value in headers.items():
        response.headers[key] = value
    return response


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle validation exceptions with 422 response - returns HTML error page."""
    raw_errors: list[dict[str, object]] = getattr(exc, "errors", list)()
    error_msgs: list[str] = []
    for e in raw_errors:
        loc = e.get("loc", ("field",))
        field = loc[-1] if isinstance(loc, (list, tuple)) and loc else "field"
        msg = e.get("msg", "Invalid")
        error_msgs.append(f"{field}: {msg}")
    error_str = "; ".join(error_msgs) if error_msgs else "Validation error"

    return await render_error_page(request, status.HTTP_422_UNPROCESSABLE_CONTENT, "Validation Error", error_str)


__all__ = [
    "conflict",
    "forbid",
    "http_exception_handler",
    "require",
    "serialize_validation_errors",
    "validation_exception_handler",
]
