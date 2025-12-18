"""Tests for UI error handling and validation."""

import pytest
from fastapi import status
from httpx import AsyncClient

from tests.fixtures.data import register_and_login, register_user


class TestUIErrorResponses:
    """Test error response handling."""

    @pytest.mark.anyio
    async def test_validation_error_returns_html_error(self, client: AsyncClient) -> None:
        """Test validation errors return HTML error page."""
        user = await register_and_login(client, role="volunteer")
        # Send invalid UUID to trigger FastAPI's path validation
        response = await client.get(
            "/opportunities/not-a-uuid",
            headers={**user.auth_header, "Accept": "text/html"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.anyio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Test unauthenticated requests return 401."""
        response = await client.get("/auth/me", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.anyio
    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        """Test 404 errors return proper status."""
        user = await register_and_login(client, role="volunteer")
        response = await client.get(
            "/opportunities/00000000-0000-0000-0000-000000000000",
            headers={**user.auth_header, "Accept": "text/html"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUIListPages:
    """Test list page rendering."""

    @pytest.mark.anyio
    async def test_followers_list_renders_html(self, client: AsyncClient) -> None:
        """Test followers endpoint returns HTML page."""
        await register_user(client, username="listtest", first_name="List", last_name="Test")
        response = await client.get(
            "/listtest/followers",
            headers={"Accept": "text/html"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.anyio
    async def test_following_list_renders_html(self, client: AsyncClient) -> None:
        """Test following endpoint returns HTML page."""
        await register_user(client, username="listtest2", first_name="List", last_name="Test2")
        response = await client.get(
            "/listtest2/following",
            headers={"Accept": "text/html"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers.get("content-type", "")


class TestHTTPMethods:
    """Test HTTP method handling."""

    @pytest.mark.anyio
    async def test_405_includes_allow_header(self, client: AsyncClient) -> None:
        """Test 405 responses include Allow header per RFC 9110."""
        response = await client.request("TRACE", "/auth/me")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert "Allow" in response.headers
        assert "GET" in response.headers["Allow"]


class TestPathParameterValidation:
    """Test path parameter regex constraints."""

    @pytest.mark.anyio
    async def test_invalid_username_returns_422(self, client: AsyncClient) -> None:
        """Test invalid username pattern returns 422."""
        response = await client.get("/invalid%20user/followers", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.anyio
    async def test_valid_username_pattern(self, client: AsyncClient) -> None:
        """Test valid username patterns are accepted."""
        response = await client.get("/valid_user-123/followers", headers={"Accept": "text/html"})
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)


class TestUIEndpoints:
    """Test endpoint rendering."""

    @pytest.mark.anyio
    async def test_profile_endpoint_returns_html(self, client: AsyncClient) -> None:
        """Test profile endpoint returns HTML."""
        await register_user(client, username="uitest", first_name="UI", last_name="Test")
        response = await client.get(
            "/uitest",
            headers={"Accept": "text/html"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers.get("content-type", "")
