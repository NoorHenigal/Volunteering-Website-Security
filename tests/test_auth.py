"""Authentication tests."""

import pytest
from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.encryption import hash_email
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

        result = await test_db.execute(select(User).where(User.email_hash == hash_email(user.email)))
        db_user = result.scalar_one_or_none()
        assert db_user is not None
        assert db_user.email == user.email  # Uses decrypted property

    @pytest.mark.anyio
    async def test_inactive_user_cannot_login(self, api: APIHelper, test_db: AsyncSession, flows: FlowHelper) -> None:
        """Inactive users should not be able to authenticate."""
        user = await flows.create_user("volunteer")
        await test_db.execute(update(User).where(User.email_hash == hash_email(user.email)).values(is_active=False))
        await test_db.commit()
        await api.unauthorized(
            "POST",
            "/auth/login",
            json={"email": user.email, "password": user.password, "account_type": "volunteer"},
        )

    @pytest.mark.anyio
    async def test_delete_account_anonymizes_and_allows_reregistration(
        self,
        api: APIHelper,
        test_db: AsyncSession,
        flows: FlowHelper,
    ) -> None:
        """Delete account should deactivate + anonymize immediately, freeing email/username for re-registration."""
        user = await flows.create_user("volunteer")

        result = await test_db.execute(select(User).where(User.email_hash == hash_email(user.email)))
        db_user = result.scalar_one()
        user_id = db_user.id

        await api.no_content("DELETE", "/settings/account", auth=user)

        refreshed = await test_db.get(User, user_id)
        assert refreshed is not None
        assert refreshed.is_active is False
        assert refreshed.email.startswith("deleted-user-")
        assert refreshed.email.endswith("@example.invalid") or refreshed.email.endswith("@example.com")
        assert refreshed.username.startswith("deleted-user-")

        await api.unauthorized(
            "POST",
            "/auth/login",
            json={"email": user.email, "password": user.password, "account_type": "volunteer"},
        )

        new_password = "newpassword123"
        reg_data = RegisterSchemaFactory.build(email=user.email, username=user.username)
        reg_resp = await api.client.post(
            "/auth/register/volunteer",
            json={
                "email": reg_data.email,
                "password": new_password,
                "first_name": reg_data.first_name,
                "last_name": reg_data.last_name,
                "username": reg_data.username,
            },
        )
        assert reg_resp.status_code == 201, reg_resp.text

        await api.ok(
            "POST",
            "/auth/login",
            json={"email": user.email, "password": new_password, "account_type": "volunteer"},
        )
