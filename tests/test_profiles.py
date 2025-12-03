"""Tests for user and organization profiles."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.data import create_organization_with_admin, register_user


@pytest.mark.anyio
async def test_user_profile_access(client: AsyncClient) -> None:
    """Test accessing a user profile."""
    await register_user(client, username="testuser", first_name="Test", last_name="User")
    response = await client.get("/testuser")
    assert response.status_code == 200
    assert "Test User" in response.text
    assert "@testuser" in response.text


@pytest.mark.anyio
async def test_organization_profile_access(client: AsyncClient, test_db: AsyncSession) -> None:
    """Test accessing an organization profile."""
    await create_organization_with_admin(client, test_db, org_name="Test Org")
    response = await client.get("/Test Org")
    assert response.status_code == 200
    assert "Test Org" in response.text


@pytest.mark.anyio
async def test_profile_not_found(client: AsyncClient) -> None:
    """Test accessing a non-existent profile."""
    response = await client.get("/nonexistent")
    assert response.status_code == 404
