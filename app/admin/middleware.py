"""Admin middleware for enforcing password reset requirements."""

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from jose import JWTError, jwt

from app.core.config import settings

ADMIN_SETUP_ALLOWED_PATHS = frozenset({"/auth/login", "/auth/admin-setup", "/auth/logout"})


async def enforce_admin_password_reset(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Block all access for admins who haven't completed password reset.

    Admins with requires_password_reset=True (indicated by 'rpr' claim in JWT)
    can only access:
    - /auth/login (login page where setup form is shown)
    - /auth/admin-setup (to submit their setup)
    - /auth/logout (to log out)
    - /static/* (static files)

    All other requests are redirected to /auth/login.
    """
    path = request.url.path

    if path.startswith("/static") or path in ADMIN_SETUP_ALLOWED_PATHS:
        return await call_next(request)

    access_token = request.cookies.get("access_token")
    if not access_token:
        return await call_next(request)

    try:
        payload = jwt.decode(
            access_token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return await call_next(request)

    user_role = payload.get("role")
    requires_password_reset = payload.get("rpr", False)

    if user_role == "system_admin" and requires_password_reset:
        return RedirectResponse(url="/auth/login", status_code=303)

    return await call_next(request)


__all__ = ["enforce_admin_password_reset"]
