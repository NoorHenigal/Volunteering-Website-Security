"""Minimal authentication roundtrip tests."""

import secrets
import string

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


def generate_random_email() -> str:
    """Generate a random email address for testing."""
    username = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    domain = "".join(secrets.choice(string.ascii_lowercase) for _ in range(6))
    return f"{username}@{domain}.com"


def generate_random_password() -> str:
    """Generate a random secure password for testing."""
    lowercase = "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
    uppercase = "".join(secrets.choice(string.ascii_uppercase) for _ in range(4))
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    special = secrets.choice("!@#$%^&*")
    return f"{lowercase}{uppercase}{digits}{special}!"


class TestAuthRoundtrip:
    """Test basic authentication roundtrip."""

    @pytest.mark.anyio
    async def test_register_login_status_logout_flow(self, client: AsyncClient, test_db: AsyncSession) -> None:
        """Test complete authentication flow: register -> login -> status -> logout."""
        email = generate_random_email()
        password = generate_random_password()

        # Register new user
        register_response = await client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "role": "volunteer"},
        )
        assert register_response.status_code == status.HTTP_201_CREATED

        # Login with registered user
        login_response = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login_response.status_code == status.HTTP_200_OK
        assert "access_token" in login_response.json()

        # Check status when logged in
        me_response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
        )
        assert me_response.status_code == status.HTTP_200_OK

        # Logout
        logout_response = await client.post("/api/auth/logout")
        assert logout_response.status_code == status.HTTP_200_OK

    @pytest.mark.anyio
    async def test_register_duplicate_email_fails(self, client: AsyncClient, test_db: AsyncSession) -> None:
        """Test registration with duplicate email fails."""
        email = generate_random_email()

        # First registration
        await client.post(
            "/api/auth/register",
            json={"email": email, "password": generate_random_password(), "role": "volunteer"},
        )

        # Second registration with same email
        response = await client.post(
            "/api/auth/register",
            json={"email": email, "password": generate_random_password(), "role": "admin"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.anyio
    async def test_register_invalid_email_fails(self, client: AsyncClient) -> None:
        """Test registration with invalid email format fails."""
        response = await client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": generate_random_password(), "role": "volunteer"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.anyio
    async def test_login_not_logged_in_fails(self, client: AsyncClient) -> None:
        """Test login with non-existent user fails."""
        response = await client.post(
            "/api/auth/login",
            json={"email": generate_random_email(), "password": generate_random_password()},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.anyio
    async def test_status_not_logged_in_fails(self, client: AsyncClient) -> None:
        """Test getting current user without authentication fails."""
        response = await client.get("/api/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.anyio
    async def test_user_persists_in_database(self, client: AsyncClient, test_db: AsyncSession) -> None:
        """Test that registered user is properly stored in database."""
        email = generate_random_email()
        password = generate_random_password()

        # Register user
        await client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "role": "organization"},
        )

        # Check user exists in database
        result = await test_db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email == email
