"""Authentication tests."""

import pytest
from httpx import AsyncClient
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
        """Test complete authentication flow: register -> login -> me redirect -> logout."""
        volunteer = await flows.create_user("volunteer")
        await api("GET", "/auth/me", expected=(200, 303), auth=volunteer)
        await api("POST", "/auth/logout", expected=(200, 303), auth=volunteer)

    @pytest.mark.anyio
    async def test_register_duplicate_email_fails(self, api: APIHelper, flows: FlowHelper) -> None:
        """Test registration with duplicate email fails (returns error page)."""
        volunteer = await flows.create_user("volunteer")
        csrf_token = api.client.cookies.get("csrf_token", "")
        response = await api.client.post(
            "/auth/register/volunteer",
            data={
                "email": volunteer.email,
                "password": "password123password123",
                "first_name": "Duplicate",
                "last_name": "User",
                "username": "duplicate_user",
                "csrf_token": csrf_token,
            },
            headers={"Accept": "text/html"},
        )
        assert response.status_code in (200, 400, 409)

    @pytest.mark.anyio
    async def test_login_nonexistent_user_fails(self, api: APIHelper) -> None:
        """Test login with non-existent user fails (returns error page)."""
        data = RegisterSchemaFactory.build()
        await api.client.get("/auth/login", headers={"Accept": "text/html"})
        csrf_token = api.client.cookies.get("csrf_token", "")
        response = await api.client.post(
            "/auth/login",
            data={
                "email": data.email,
                "password": data.password.get_secret_value(),
                "account_type": "volunteer",
                "csrf_token": csrf_token,
            },
            headers={"Accept": "text/html"},
        )
        assert response.status_code in (200, 401)
        if response.status_code == 200:
            assert "error" in response.text.lower() or "invalid" in response.text.lower()

    @pytest.mark.anyio
    async def test_status_unauthenticated_returns_401(self, api: APIHelper) -> None:
        """Test getting current user without authentication returns 401."""
        await api("GET", "/auth/me", expected=401)

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
        """Inactive users should not be able to authenticate (returns error page)."""
        user = await flows.create_user("volunteer")
        await test_db.execute(update(User).where(User.email_hash == hash_email(user.email)).values(is_active=False))
        await test_db.commit()
        csrf_token = api.client.cookies.get("csrf_token", "")
        response = await api.client.post(
            "/auth/login",
            data={
                "email": user.email,
                "password": user.password,
                "account_type": "volunteer",
                "csrf_token": csrf_token,
            },
            headers={"Accept": "text/html"},
        )
        # Returns 200 or 401 with error message
        assert response.status_code in (200, 401)
        if response.status_code == 200:
            assert (
                "error" in response.text.lower()
                or "invalid" in response.text.lower()
                or "inactive" in response.text.lower()
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

        await api.ok("POST", "/settings/account/delete", auth=user)

        refreshed = await test_db.get(User, user_id)
        assert refreshed is not None
        assert refreshed.is_active is False
        assert refreshed.email.startswith("deleted-user-")
        assert refreshed.email.endswith("@example.invalid") or refreshed.email.endswith("@example.com")
        assert refreshed.username.startswith("deleted-user-")

        # Login with old credentials should fail
        csrf_token = api.client.cookies.get("csrf_token", "")
        login_resp = await api.client.post(
            "/auth/login",
            data={
                "email": user.email,
                "password": user.password,
                "account_type": "volunteer",
                "csrf_token": csrf_token,
            },
            headers={"Accept": "text/html"},
        )
        assert login_resp.status_code in (200, 401)

        new_password = "newpassword123newpassword123"
        reg_data = RegisterSchemaFactory.build(email=user.email, username=user.username)
        csrf_token2 = api.client.cookies.get("csrf_token", "")
        reg_resp = await api.client.post(
            "/auth/register/volunteer",
            data={
                "email": reg_data.email,
                "password": new_password,
                "first_name": reg_data.first_name,
                "last_name": reg_data.last_name,
                "username": reg_data.username,
                "csrf_token": csrf_token2,
            },
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert reg_resp.status_code in (200, 303), reg_resp.text

        # Login with new password should work
        csrf_token3 = api.client.cookies.get("csrf_token", "")
        login_resp2 = await api.client.post(
            "/auth/login",
            data={
                "email": user.email,
                "password": new_password,
                "account_type": "volunteer",
                "csrf_token": csrf_token3,
            },
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert login_resp2.status_code in (200, 303)

    @pytest.mark.anyio
    async def test_api_keys_loaded_correctly(self) -> None:
        """Critical: Verify API keys loaded correctly."""
        from app.core.config import settings

        assert settings.jwt_secret_key is not None
        jwt_value = settings.jwt_secret_key.get_secret_value()
        assert len(jwt_value) > 20, "JWT key should be at least 20 characters"

        assert settings.encryption_key is not None
        encryption_value = settings.encryption_key.get_secret_value()
        assert len(encryption_value) == 64, "Encryption key must be exactly 64 hex characters"

    @pytest.mark.anyio
    async def test_auth_library_initialized(self, client: AsyncClient) -> None:
        """Critical: Verify library initialized correctly."""
        response = await client.get("/auth/me", headers={"Accept": "text/html"})
        # Returns 401 when not authenticated
        assert response.status_code == 401, f"Auth system may not be initialized properly, got {response.status_code}"
