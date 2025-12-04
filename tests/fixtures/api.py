"""Simplified API testing helper."""

from typing import Any

from httpx import AsyncClient, Response

from tests.fixtures.data import AuthenticatedUser


class APIHelper:
    """Simplified API testing helper with universal request method."""

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
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | Response:
        """Universal request method.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint path
            expected: Expected status code(s). If None, accepts any 2xx.
            auth: Authenticated user for Authorization header
            json: JSON body data
            **kwargs: Additional request arguments

        Returns:
            JSON dict for success responses, Response object for errors.
        """
        headers = kwargs.pop("headers", {})
        if auth:
            headers.update(auth.auth_header)

        response = await self.client.request(method, endpoint, headers=headers, json=json, **kwargs)

        if expected is not None:
            expected_codes = expected if isinstance(expected, tuple) else (expected,)
            assert response.status_code in expected_codes, (
                f"Expected {expected_codes}, got {response.status_code}: {response.text}"
            )

        # Return JSON for success, Response for errors
        if 200 <= response.status_code < 300:
            try:
                json_result: dict[str, Any] = response.json()
            except (ValueError, TypeError):
                return response
            else:
                return json_result
        return response

    async def ok(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Assert success (200/201) and return JSON."""
        result = await self(method, endpoint, expected=(200, 201), auth=auth, json=json, **kwargs)
        assert isinstance(result, dict)
        return result

    async def created(
        self,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Assert 201 Created and return JSON."""
        result = await self("POST", endpoint, expected=201, auth=auth, json=json, **kwargs)
        assert isinstance(result, dict)
        return result

    async def forbidden(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 403 Forbidden."""
        result = await self(method, endpoint, expected=403, auth=auth, json=json, **kwargs)
        assert isinstance(result, Response)
        return result

    async def unauthorized(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 401 Unauthorized."""
        result = await self(method, endpoint, expected=401, json=json, **kwargs)
        assert isinstance(result, Response)
        return result

    async def not_found(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 404 Not Found."""
        result = await self(method, endpoint, expected=404, auth=auth, json=json, **kwargs)
        assert isinstance(result, Response)
        return result

    async def bad_request(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 400 Bad Request."""
        result = await self(method, endpoint, expected=400, auth=auth, json=json, **kwargs)
        assert isinstance(result, Response)
        return result

    async def unprocessable(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 422 Unprocessable Entity."""
        result = await self(method, endpoint, expected=422, auth=auth, json=json, **kwargs)
        assert isinstance(result, Response)
        return result

    async def conflict(
        self,
        method: str,
        endpoint: str,
        *,
        auth: AuthenticatedUser | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Response:
        """Assert 409 Conflict."""
        result = await self(method, endpoint, expected=409, auth=auth, json=json, **kwargs)
        assert isinstance(result, Response)
        return result

    async def list_contains(
        self,
        endpoint: str,
        *,
        auth: AuthenticatedUser,
        expected_count: int | None = None,
    ) -> dict[str, Any]:
        """Assert list endpoint returns expected items."""
        data = await self.ok("GET", endpoint, auth=auth)
        assert "items" in data
        if expected_count is not None:
            assert len(data["items"]) == expected_count
        return data
