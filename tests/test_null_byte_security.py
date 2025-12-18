"""Test null byte handling across all input vectors."""

from typing import ClassVar

import pytest
from fastapi import status
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import VolunteerRegisterSchema
from app.opportunities.schemas import OpportunityCreate
from app.organizations.schemas import OrganizationCreate
from app.profiles.schemas import ProfileUpdateSchema
from tests.fixtures.api import APIHelper
from tests.fixtures.flows import FlowHelper

TEST_PWD = "TestPass123!TestPwd"


class TestNullByteRejection:
    """Test that null bytes are properly rejected at all levels."""

    NULL_BYTE_STRINGS: ClassVar[list[str]] = [
        "test\x00",
        "\x00test",
        "te\x00st",
        "test\x00\x00",
        "\x00",
    ]

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_email(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in email field."""
        for null_string in self.NULL_BYTE_STRINGS:
            response = await api.client.post(
                "/auth/register/volunteer",
                json={
                    "email": f"test{null_string}@example.com",
                    "password": "TestPass123!TestPwd",
                    "first_name": "Test",
                    "last_name": "User",
                    "username": "testuser123",
                },
            )
            # Should fail validation (422) or bad request (400)
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_password(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in password field."""
        for null_string in self.NULL_BYTE_STRINGS:
            response = await api.client.post(
                "/auth/register/volunteer",
                json={
                    "email": "test@example.com",
                    "password": f"TestPass{null_string}123!",
                    "first_name": "Test",
                    "last_name": "User",
                    "username": "testuser123",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_names(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in name fields."""
        for null_string in self.NULL_BYTE_STRINGS:
            # Test first_name
            response = await api.client.post(
                "/auth/register/volunteer",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!TestPwd",
                    "first_name": f"Test{null_string}",
                    "last_name": "User",
                    "username": "testuser123",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

            # Test last_name
            response = await api.client.post(
                "/auth/register/volunteer",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!TestPwd",
                    "first_name": "Test",
                    "last_name": f"User{null_string}",
                    "username": "testuser123",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_username(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in username field."""
        for null_string in self.NULL_BYTE_STRINGS:
            response = await api.client.post(
                "/auth/register/volunteer",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!TestPwd",
                    "first_name": "Test",
                    "last_name": "User",
                    "username": f"testuser{null_string}",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_organization_creation_rejects_null_bytes(self, api: APIHelper, flows: FlowHelper) -> None:
        """Test that organization creation rejects null bytes."""
        org_user = await flows.create_user("volunteer")
        csrf_token = api.client.cookies.get("csrf_token", "")

        for null_string in self.NULL_BYTE_STRINGS:
            # Test name field
            response = await api.client.post(
                "/organizations",
                data={
                    "name": f"TestOrg{null_string}",
                    "username": "testorg",
                    "description": "Test description",
                    "csrf_token": csrf_token,
                },
                headers={**org_user.auth_header, "Accept": "text/html"},
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

            # Test description field
            response = await api.client.post(
                "/organizations",
                data={
                    "name": "TestOrg",
                    "username": "testorg",
                    "description": f"Test{null_string}",
                    "csrf_token": csrf_token,
                },
                headers={**org_user.auth_header, "Accept": "text/html"},
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_opportunity_creation_rejects_null_bytes(
        self, api: APIHelper, flows: FlowHelper, test_db: AsyncSession
    ) -> None:
        """Test that opportunity creation rejects null bytes."""
        from sqlalchemy import select

        from app.db.models import Organization

        org_user = await flows.create_user("volunteer")
        org = await flows.create_org(org_user)
        csrf_token = api.client.cookies.get("csrf_token", "")

        # Get actual org ID from database
        result = await test_db.execute(select(Organization).where(Organization.username == org["username"]))
        db_org = result.scalar_one()
        org_id = str(db_org.id)

        for null_string in self.NULL_BYTE_STRINGS:
            # Test title field
            response = await api.client.post(
                "/opportunities",
                data={
                    "title": f"TestOpp{null_string}",
                    "description": "Test description",
                    "organization_id": org_id,
                    "csrf_token": csrf_token,
                },
                headers={**org_user.auth_header, "Accept": "text/html"},
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

            # Test description field
            response = await api.client.post(
                "/opportunities",
                data={
                    "title": "TestOpp",
                    "description": f"Test{null_string}",
                    "organization_id": org_id,
                    "csrf_token": csrf_token,
                },
                headers={**org_user.auth_header, "Accept": "text/html"},
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_pydantic_schema_validation_rejects_null_bytes(self) -> None:
        """Test that Pydantic schemas reject null bytes at validation level."""
        # Test VolunteerRegisterSchema
        with pytest.raises(ValidationError):
            VolunteerRegisterSchema(
                email="test\x00@example.com",
                password=SecretStr(TEST_PWD),
                first_name="Test",
                last_name="User",
                username="testuser",
            )

        # Test OrganizationCreate
        with pytest.raises(ValidationError):
            OrganizationCreate(
                name="Test\x00Org",
                username="testorg",
                description="Test",
            )

        # Test OpportunityCreate - this will fail because we need a valid UUID
        # but we're testing the string fields
        from uuid import uuid4

        with pytest.raises(ValidationError):
            OpportunityCreate(
                title="Test\x00Opp",
                description="Test",
                location="Test",
                organization_id=uuid4(),
            )

        # Test ProfileUpdateSchema
        with pytest.raises(ValidationError):
            ProfileUpdateSchema(bio="Test\x00bio")
