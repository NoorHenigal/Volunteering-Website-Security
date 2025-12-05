"""Authentication tests."""

import pytest
from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from tests.fixtures.api import APIHelper
from tests.fixtures.data import RegisterSchemaFactory
from tests.fixtures.flows import FlowHelper


class TestAuthRoundtrip:
    """Test basic authentication roundtrip."""

    @pytest.mark.anyio
    async def test_register_login_status_logout_flow(
        self,
        api: APIHelper,
        flows: FlowHelper,
    ) -> None:
        """Test complete authentication flow: register -> login -> status -> logout."""
        volunteer = await flows.create_user("volunteer")
        await api("GET", "/auth/me", expected=status.HTTP_200_OK, auth=volunteer)
        await api("POST", "/auth/logout", expected=status.HTTP_200_OK)

    @pytest.mark.anyio
    async def test_register_duplicate_email_fails(self, api: APIHelper, flows: FlowHelper) -> None:
        """Test registration with duplicate email fails."""
        volunteer = await flows.create_user("volunteer")
        RegisterSchemaFactory.build()
        await api.client.post(
            "/auth/register",
            json={
                "email": volunteer.email,
                "password": "password123",
                "role": "volunteer",
                "first_name": "Duplicate",
                "last_name": "User",
                "username": "duplicate_user",
            },
        )

    @pytest.mark.anyio
    async def test_login_nonexistent_user_fails(self, api: APIHelper) -> None:
        """Test login with non-existent user fails."""
        data = RegisterSchemaFactory.build()
        await api.unauthorized("POST", "/auth/login", json={"email": data.email, "password": data.password})

    @pytest.mark.anyio
    async def test_status_unauthenticated_fails(self, api: APIHelper) -> None:
        """Test getting current user without authentication fails."""
        await api.unauthorized("GET", "/auth/me")

    @pytest.mark.anyio
    async def test_user_persists_in_database(self, api: APIHelper, test_db: AsyncSession, flows: FlowHelper) -> None:
        """Test that registered user is properly stored in database."""
        user = await flows.create_user("organization")

        result = await test_db.execute(select(User).where(User.email == user.email))
        db_user = result.scalar_one_or_none()
        assert db_user is not None
        assert db_user.email == user.email
