"""Tests for API design."""

import pytest
from fastapi import status
from httpx import AsyncClient

from tests.fixtures.data import register_and_login


class TestHealthEndpoint:
    """Test health endpoint with proper response model."""

    @pytest.mark.anyio
    async def test_health_returns_structured_response(self, client: AsyncClient) -> None:
        """Test /health returns HealthResponse schema."""
        response = await client.get("/health", headers={"Accept": "application/json"})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    @pytest.mark.anyio
    async def test_health_openapi_schema(self, client: AsyncClient) -> None:
        """Test /health is documented in OpenAPI schema."""
        response = await client.get("/openapi.json")
        assert response.status_code == status.HTTP_200_OK
        schema = response.json()
        assert "/health" in schema["paths"]
        health_get = schema["paths"]["/health"]["get"]
        assert "responses" in health_get
        assert "200" in health_get["responses"]


class TestErrorResponses:
    """Test consistent error response format."""

    @pytest.mark.anyio
    async def test_validation_error_returns_structured_response(self, client: AsyncClient) -> None:
        """Test validation errors return ErrorResponse schema.

        Note: Auth router handles its own validation errors with ctx.error_response(),
        so we test the global exception handler via a different endpoint.
        """
        user = await register_and_login(client, role="volunteer")
        # Send invalid UUID to trigger FastAPI's path validation
        response = await client.get(
            "/api/opportunities/not-a-uuid",
            headers=user.auth_header,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert "detail" in data
        assert "status_code" in data
        assert data["status_code"] == 422

    @pytest.mark.anyio
    async def test_http_exception_returns_structured_response(self, client: AsyncClient) -> None:
        """Test HTTP exceptions return ErrorResponse schema."""
        response = await client.get("/api/auth/me")  # No auth = 401
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert "detail" in data
        assert "status_code" in data
        assert data["status_code"] == 401

    @pytest.mark.anyio
    async def test_not_found_returns_structured_response(self, client: AsyncClient) -> None:
        """Test 404 errors return ErrorResponse schema."""
        user = await register_and_login(client, role="volunteer")
        response = await client.get(
            "/api/opportunities/00000000-0000-0000-0000-000000000000",
            headers=user.auth_header,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "status_code" in data


class TestListResponseFormat:
    """Test ListResponse format with optional pagination meta."""

    @pytest.mark.anyio
    async def test_followers_list_uses_list_response(self, client: AsyncClient) -> None:
        """Test followers endpoint returns ListResponse format."""
        from tests.fixtures.data import register_user

        await register_user(client, username="listtest", first_name="List", last_name="Test")
        response = await client.get(
            "/listtest/followers",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.anyio
    async def test_following_list_uses_list_response(self, client: AsyncClient) -> None:
        """Test following endpoint returns ListResponse format."""
        from tests.fixtures.data import register_user

        await register_user(client, username="listtest2", first_name="List", last_name="Test2")
        response = await client.get(
            "/listtest2/following",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)


class TestOpenAPIDocumentation:
    """Test OpenAPI documentation improvements."""

    @pytest.mark.anyio
    async def test_auth_api_endpoints_documented(self, client: AsyncClient) -> None:
        """Test auth API endpoints have response documentation."""
        response = await client.get("/openapi.json")
        assert response.status_code == status.HTTP_200_OK
        schema = response.json()

        # Check /api/auth/register has responses documented
        register_path = schema["paths"].get("/api/auth/register", {}).get("post", {})
        assert "responses" in register_path
        assert "201" in register_path["responses"] or "200" in register_path["responses"]

    @pytest.mark.anyio
    async def test_error_response_schema_in_openapi(self, client: AsyncClient) -> None:
        """Test ErrorResponse schema is defined in OpenAPI."""
        response = await client.get("/openapi.json")
        assert response.status_code == status.HTTP_200_OK
        schema = response.json()

        # Check ErrorResponse is in components/schemas
        schemas = schema.get("components", {}).get("schemas", {})
        assert "ErrorResponse" in schemas
        error_schema = schemas["ErrorResponse"]
        assert "detail" in error_schema.get("properties", {})

    @pytest.mark.anyio
    async def test_health_response_schema_in_openapi(self, client: AsyncClient) -> None:
        """Test HealthResponse schema is defined in OpenAPI."""
        response = await client.get("/openapi.json")
        assert response.status_code == status.HTTP_200_OK
        schema = response.json()

        schemas = schema.get("components", {}).get("schemas", {})
        assert "HealthResponse" in schemas
        health_schema = schemas["HealthResponse"]
        assert "status" in health_schema.get("properties", {})


class TestExceptionHandlers:
    """Test exception handlers for RFC compliance and schema correctness."""

    @pytest.mark.anyio
    async def test_validation_error_returns_array_detail(self, client: AsyncClient) -> None:
        """Test 422 responses have detail as array per OpenAPI schema."""
        user = await register_and_login(client, role="volunteer")
        response = await client.get("/api/opportunities/invalid-uuid", headers=user.auth_header)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert isinstance(data["detail"], list)  # Not string
        assert all("loc" in err and "msg" in err for err in data["detail"])

    @pytest.mark.anyio
    async def test_405_includes_allow_header(self, client: AsyncClient) -> None:
        """Test 405 responses include Allow header per RFC 9110."""
        response = await client.request("TRACE", "/health")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert "Allow" in response.headers
        assert "GET" in response.headers["Allow"]


class TestPathParameterValidation:
    """Test path parameter regex constraints."""

    @pytest.mark.anyio
    async def test_invalid_username_returns_422(self, client: AsyncClient) -> None:
        """Test invalid username pattern returns 422."""
        response = await client.get("/invalid%20user/followers")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.anyio
    async def test_valid_username_pattern(self, client: AsyncClient) -> None:
        """Test valid username patterns are accepted."""
        # Will return 404 (user not found) not 422 (validation error)
        response = await client.get("/valid_user-123/followers")
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)


class TestDualPurposeEndpoints:
    """Test dual-purpose endpoints handle both UI and API correctly."""

    @pytest.mark.anyio
    async def test_profile_endpoint_returns_json_for_api(self, client: AsyncClient) -> None:
        """Test profile endpoint returns JSON for API requests."""
        from tests.fixtures.data import register_user

        await register_user(client, username="apitest", first_name="API", last_name="Test")
        response = await client.get(
            "/apitest",
            headers={"Accept": "application/json"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "username" in data

    @pytest.mark.anyio
    async def test_profile_endpoint_returns_html_for_ui(self, client: AsyncClient) -> None:
        """Test profile endpoint returns HTML for UI requests."""
        from tests.fixtures.data import register_user

        await register_user(client, username="uitest", first_name="UI", last_name="Test")
        response = await client.get(
            "/uitest",
            headers={"Accept": "text/html"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers.get("content-type", "")
