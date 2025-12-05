"""Global exception handlers for consistent error responses."""

import json
from collections.abc import Sequence

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.routing import Match

HTTP_405_METHOD_NOT_ALLOWED = 405


def serialize_validation_errors(errors: Sequence[object]) -> list[object]:
    """Serialize validation errors to JSON-safe format.

    Args:
        errors: Sequence of validation error dictionaries

    Returns:
        JSON-serializable list of error dictionaries
    """
    return json.loads(json.dumps(list(errors), default=str))  # type: ignore[no-any-return]


def require[T](entity: T | None, message: str, code: int = status.HTTP_404_NOT_FOUND) -> T:
    """Require entity to exist, otherwise raise HTTPException.

    Args:
        entity: Entity to check
        message: Error message if entity is None
        code: HTTP status code (default 404)

    Returns:
        Entity if it exists

    Raises:
        HTTPException: If entity is None
    """
    if entity is None:
        raise HTTPException(status_code=code, detail=message)
    return entity


def forbid(condition: bool, message: str) -> None:
    """Raise 403 Forbidden if condition is True.

    Args:
        condition: If True, raises HTTPException
        message: Error message for the exception

    Raises:
        HTTPException: 403 Forbidden if condition is True
    """
    if condition:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def conflict(condition: bool, message: str) -> None:
    """Raise 409 Conflict if condition is True.

    Args:
        condition: If True, raises HTTPException
        message: Error message for the exception

    Raises:
        HTTPException: 409 Conflict if condition is True
    """
    if condition:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle HTTP exceptions with structured ErrorResponse.

    For 405 responses, includes RFC 9110 compliant Allow header.
    """
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc))
    headers: dict[str, str] = getattr(exc, "headers", None) or {}

    if status_code == HTTP_405_METHOD_NOT_ALLOWED:
        # Compute allowed methods for RFC 9110 compliance
        # Check for PARTIAL match (path matches but method doesn't) or FULL match
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

    return JSONResponse(
        status_code=status_code,
        content={"detail": str(detail), "status_code": status_code, "error_code": None},
        headers=headers,
    )


async def validation_exception_handler(_request: Request, exc: Exception) -> Response:
    """Handle validation exceptions with proper array format per OpenAPI schema."""
    # exc.errors() returns structured array for RequestValidationError
    errors: list[dict[str, object]] = getattr(exc, "errors", list)()

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": serialize_validation_errors(errors), "status_code": 422},
    )


__all__ = [
    "conflict",
    "forbid",
    "http_exception_handler",
    "require",
    "serialize_validation_errors",
    "validation_exception_handler",
]
