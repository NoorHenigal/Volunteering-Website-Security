"""Organizations tests."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Organization, UserOrganizationRole
from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext, get_user_from_db
from tests.fixtures.flows import FlowHelper


class TestOrganizationAPI:
    """Test organization API endpoints."""

    @pytest.mark.anyio
    async def test_create_organization(
        self,
        api: APIHelper,
        flows: FlowHelper,
        test_db: AsyncSession,
    ) -> None:
        """Creating an organization also makes the creator an admin (DB check)."""
        org_user = await flows.create_user("organization")

        data = await api.created(
            "/organizations",
            auth=org_user,
            json={
                "name": "Sustainability Society",
                "description": "Sustainability society...",
            },
        )

        assert data["name"] == "Sustainability Society"
        assert data["description"] == "Sustainability society..."
        assert "id" in data

        # DB verification: creator is stored as admin
        org_result = await test_db.execute(select(Organization).where(Organization.name == "Sustainability Society"))
        org = org_result.scalar_one_or_none()
        assert org is not None

        user = await get_user_from_db(test_db, org_user.email)
        result = await test_db.execute(
            select(UserOrganizationRole).where(
                UserOrganizationRole.user_id == user.id,
                UserOrganizationRole.organization_id == org.id,
            )
        )
        user_role = result.scalar_one_or_none()
        assert user_role is not None
        assert user_role.role == "admin"

    @pytest.mark.anyio
    async def test_list_organizations(
        self,
        api: APIHelper,
        flows: FlowHelper,
    ) -> None:
        """Test listing all organizations."""
        # Create orgs via API (not DB)
        org_user = await flows.create_user("organization")
        await flows.create_org(org_user, name="Campus Food Bank", description="On-campus food support")
        await flows.create_org(org_user, name="Park Clean-Up Group", description="Local park volunteering")

        volunteer = await flows.create_user("volunteer")
        data = await api.ok("GET", "/organizations", auth=volunteer)
        assert "items" in data
        assert len(data["items"]) >= 2

    @pytest.mark.anyio
    async def test_get_organization_details(
        self,
        api: APIHelper,
        flows: FlowHelper,
        test_db: AsyncSession,
    ) -> None:
        """Test getting organization details with members."""
        # Create org via API
        org_user = await flows.create_user("organization")
        org = await flows.create_org(org_user, name="Test Org", description="Test description")

        # Add member via flows helper
        member = await flows.create_user("volunteer")
        await flows.add_member(test_db, member, org, role="member")

        data = await api.ok("GET", f"/organizations/{org['id']}", auth=member)
        assert data["name"] == "Test Org"
        assert data["description"] == "Test description"
        assert "members" in data
        # Should have admin + member
        assert len(data["members"]) == 2

    @pytest.mark.anyio
    async def test_update_organization_as_admin(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test updating organization as admin."""
        test_org = await ctx.organization()
        data = await api.ok(
            "PUT",
            f"/organizations/{test_org.organization.id}",
            auth=test_org.admin,
            json={"name": "New Name", "description": "New description"},
        )
        assert data["name"] == "New Name"
        assert data["description"] == "New description"

    @pytest.mark.anyio
    async def test_update_organization_as_non_admin_fails(
        self,
        api: APIHelper,
        flows: FlowHelper,
        test_db: AsyncSession,
    ) -> None:
        """Test that non-admins cannot update organization."""
        # Create org via API
        org_user = await flows.create_user("organization")
        org = await flows.create_org(org_user, name="Test Org", description="Test description")

        # Add member via flows helper
        member = await flows.create_user("volunteer")
        await flows.add_member(test_db, member, org, role="member")

        await api.forbidden("PUT", f"/organizations/{org['id']}", auth=member, json={"name": "New Name"})

    @pytest.mark.anyio
    async def test_unauthenticated_cannot_create_organization(self, api: APIHelper) -> None:
        """Test that unauthenticated users cannot create organizations."""
        await api.unauthorized(
            "POST",
            "/organizations",
            json={"name": "Test Org", "description": "Test description"},
        )
