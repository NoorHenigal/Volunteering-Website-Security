"""Testing helper."""

from typing import Any

from httpx import AsyncClient, Response

from tests.fixtures.data import AuthenticatedUser


class APIHelper:
    """Testing helper with form-based submissions and cookie auth."""

    def __init__(self, client: AsyncClient) -> None:
        """Initialize with an AsyncClient instance."""
        self.client = client

    async def __call__(
        self,
        method: str,
        endpoint: str,
        *,
        expected: int | tuple[int, ...] | None = None,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Universal request method for testing.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint path
            expected: Expected status code(s). If None, accepts any 2xx or 3xx.
            auth: Authenticated user for cookie-based auth
            data: Form data to submit
            **kwargs: Additional request arguments

        Returns:
            Response object.
        """
        headers = kwargs.pop("headers", {})
        headers["Accept"] = "text/html"
        if auth:
            headers.update(auth.auth_header)

        # Include CSRF token in form data for POST/PUT/PATCH/DELETE
        if data is not None and method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            csrf_token = self.client.cookies.get("csrf_token")
            if csrf_token and "csrf_token" not in data:
                data = {**data, "csrf_token": csrf_token}

        response = await self.client.request(method, endpoint, headers=headers, data=data, **kwargs)

        if expected is not None:
            expected_codes = expected if isinstance(expected, tuple) else (expected,)
            assert response.status_code in expected_codes, (
                f"Expected {expected_codes}, got {response.status_code}: {response.text}"
            )

        return response

    async def ok(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert success (200/303) and return Response."""
        return await self(method, endpoint, expected=(200, 303), auth=auth, data=data, **kwargs)

    async def created(
        self,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert success (200/303 for testing) and return Response."""
        return await self("POST", endpoint, expected=(200, 303), auth=auth, data=data, **kwargs)

    async def forbidden(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 403 Forbidden."""
        return await self(method, endpoint, expected=403, auth=auth, data=data, **kwargs)

    async def unauthorized(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 401 Unauthorized or 303 redirect to login."""
        return await self(method, endpoint, expected=(401, 303), data=data, **kwargs)

    async def not_found(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 404 Not Found."""
        return await self(method, endpoint, expected=404, auth=auth, data=data, **kwargs)

    async def bad_request(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 400 Bad Request."""
        return await self(method, endpoint, expected=400, auth=auth, data=data, **kwargs)

    async def unprocessable(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 422 Unprocessable Entity."""
        return await self(method, endpoint, expected=422, auth=auth, data=data, **kwargs)

    async def conflict(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 409 Conflict or 400."""
        return await self(method, endpoint, expected=(409, 400), auth=auth, data=data, **kwargs)

    async def redirect(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 303 redirect."""
        return await self(method, endpoint, expected=303, auth=auth, data=data, **kwargs)

    async def html_contains(
        self,
        endpoint: str,
        *,
        auth: AuthenticatedUser,
        text: str,
    ) -> Response:
        """Assert HTML response contains expected text."""
        response = await self.ok("GET", endpoint, auth=auth)
        assert text in response.text, f"Expected '{text}' in response"
        return response
