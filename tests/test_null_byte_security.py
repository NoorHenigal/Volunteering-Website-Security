"""Test null byte handling across all input vectors."""

from typing import ClassVar

import pytest
from fastapi import status
from pydantic import ValidationError

from app.auth.schemas import RegisterSchema
from app.opportunities.schemas import OpportunityCreate
from app.organizations.schemas import OrganizationCreate
from app.profiles.schemas import ProfileUpdateSchema
from tests.fixtures.api import APIHelper
from tests.fixtures.flows import FlowHelper


class TestNullByteRejection:
    """Test that null bytes are properly rejected at all levels."""

    # Test data with null bytes in various positions
    NULL_BYTE_STRINGS: ClassVar[list[str]] = [
        "test\x00",  # Null byte at end
        "\x00test",  # Null byte at start
        "te\x00st",  # Null byte in middle
        "test\x00\x00",  # Multiple null bytes
        "\x00",  # Only null byte
    ]

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_email(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in email field."""
        for null_string in self.NULL_BYTE_STRINGS:
            response = await api.client.post(
                "/auth/register",
                json={
                    "email": f"test{null_string}@example.com",
                    "password": "TestPass123!",
                    "role": "volunteer",
                    "first_name": "Test",
                    "last_name": "User",
                    "username": "testuser123",
                },
            )
            # Should fail validation (422) or bad request (400)
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in email was not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_password(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in password field."""
        for null_string in self.NULL_BYTE_STRINGS:
            response = await api.client.post(
                "/auth/register",
                json={
                    "email": "test@example.com",
                    "password": f"TestPass{null_string}123!",
                    "role": "volunteer",
                    "first_name": "Test",
                    "last_name": "User",
                    "username": "testuser123",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in password was not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_names(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in name fields."""
        for null_string in self.NULL_BYTE_STRINGS:
            # Test first_name
            response = await api.client.post(
                "/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!",
                    "role": "volunteer",
                    "first_name": f"Test{null_string}",
                    "last_name": "User",
                    "username": "testuser123",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in first_name was not rejected: {null_string!r}"

            # Test last_name
            response = await api.client.post(
                "/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!",
                    "role": "volunteer",
                    "first_name": "Test",
                    "last_name": f"User{null_string}",
                    "username": "testuser123",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in last_name was not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_registration_rejects_null_bytes_in_username(self, api: APIHelper) -> None:
        """Test that registration rejects null bytes in username field."""
        for null_string in self.NULL_BYTE_STRINGS:
            response = await api.client.post(
                "/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!",
                    "role": "volunteer",
                    "first_name": "Test",
                    "last_name": "User",
                    "username": f"testuser{null_string}",
                },
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in username was not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_organization_creation_rejects_null_bytes(self, api: APIHelper, flows: FlowHelper) -> None:
        """Test that organization creation rejects null bytes."""
        org_user = await flows.create_user("organization")

        for null_string in self.NULL_BYTE_STRINGS:
            # Test name field
            response = await api.client.post(
                "/organizations",
                json={
                    "name": f"TestOrg{null_string}",
                    "description": "Test description",
                },
                headers=org_user.auth_header,
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in organization name was not rejected: {null_string!r}"

            # Test description field
            response = await api.client.post(
                "/organizations",
                json={
                    "name": "TestOrg",
                    "description": f"Test{null_string}",
                },
                headers=org_user.auth_header,
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in organization description was not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_opportunity_creation_rejects_null_bytes(self, api: APIHelper, flows: FlowHelper) -> None:
        """Test that opportunity creation rejects null bytes."""
        org_user = await flows.create_user("organization")
        org = await flows.create_org(org_user)

        for null_string in self.NULL_BYTE_STRINGS:
            # Test title field
            response = await api.client.post(
                "/opportunities",
                json={
                    "title": f"TestOpp{null_string}",
                    "description": "Test description",
                    "organization_id": org["id"],
                },
                headers=org_user.auth_header,
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in opportunity title was not rejected: {null_string!r}"

            # Test description field
            response = await api.client.post(
                "/opportunities",
                json={
                    "title": "TestOpp",
                    "description": f"Test{null_string}",
                    "organization_id": org["id"],
                },
                headers=org_user.auth_header,
            )
            assert response.status_code in [
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                status.HTTP_400_BAD_REQUEST,
            ], f"Null byte in opportunity description was not rejected: {null_string!r}"

    @pytest.mark.anyio
    async def test_pydantic_schema_validation_rejects_null_bytes(self) -> None:
        """Test that Pydantic schemas reject null bytes at validation level."""
        # Test RegisterSchema
        with pytest.raises(ValidationError):
            RegisterSchema(
                email="test\x00@example.com",
                password="TestPass123!",  # noqa: S106
                role="volunteer",
                first_name="Test",
                last_name="User",
                username="testuser",
            )

        # Test OrganizationCreate
        with pytest.raises(ValidationError):
            OrganizationCreate(name="Test\x00Org", description="Test")

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
