"""Organizations tests."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Organization, UserOrganizationRole
from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext
from tests.fixtures.flows import FlowHelper


class TestOrganizationUI:
    """Test organization endpoints."""

    @pytest.mark.anyio
    async def test_create_organization(
        self,
        api: APIHelper,
        flows: FlowHelper,
        test_db: AsyncSession,
    ) -> None:
        """Creating an organization also makes the creator an admin (DB check)."""
        response = await api.client.post(
            "/auth/register/organization",
            data={
                "name": "Sustainability Society",
                "username": "sustainability-society",
                "email": "sustainability@example.com",
                "password": "TestPass123!TestPwd",
            },
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)
        org_result = await test_db.execute(select(Organization).where(Organization.name == "Sustainability Society"))
        org = org_result.scalar_one_or_none()
        assert org is not None

        result = await test_db.execute(
            select(UserOrganizationRole).where(
                UserOrganizationRole.organization_id == org.id,
                UserOrganizationRole.role == "admin",
            )
        )
        user_role = result.scalar_one_or_none()
        assert user_role is not None

    @pytest.mark.anyio
    async def test_list_organizations(
        self,
        api: APIHelper,
        flows: FlowHelper,
    ) -> None:
        """Test listing all organizations."""
        user = await flows.create_user("volunteer")
        await flows.create_org(user, name="Campus Food Bank", description="On-campus food support")
        await flows.create_org(user, name="Park Clean-Up Group", description="Local park volunteering")

        volunteer = await flows.create_user("volunteer")
        response = await api.ok("GET", "/organizations", auth=volunteer)
        assert response.status_code == 200
        assert "Organizations" in response.text

    @pytest.mark.anyio
    async def test_get_organization_details(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test viewing organization details page."""
        test_org = await ctx.organization()
        volunteer = await ctx.volunteer()

        response = await api.ok("GET", f"/organizations/{test_org.organization.id}", auth=volunteer)
        assert response.status_code == 200
        assert test_org.organization.name in response.text

    @pytest.mark.anyio
    async def test_update_organization_as_admin(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test updating organization as admin."""
        test_org = await ctx.organization()
        response = await api.ok(
            "POST",
            f"/organizations/{test_org.organization.id}/edit",
            auth=test_org.admin,
            data={"name": "New Name", "description": "New description"},
        )
        assert response.status_code in (200, 303)

    @pytest.mark.anyio
    async def test_update_organization_as_non_admin_fails(
        self,
        api: APIHelper,
        flows: FlowHelper,
        test_db: AsyncSession,
        ctx: FixtureContext,
    ) -> None:
        """Test that non-admins cannot update organization."""
        test_org = await ctx.organization()

        member = await flows.create_user("volunteer")
        await flows.add_member(test_db, member, test_org, role="member")

        response = await api.forbidden(
            "POST",
            f"/organizations/{test_org.organization.id}/edit",
            auth=member,
            data={"name": "New Name"},
        )
        assert response.status_code == 403

    @pytest.mark.anyio
    async def test_unauthenticated_can_register_organization(self, api: APIHelper) -> None:
        """Test that unauthenticated users can create organization accounts via registration."""
        response = await api.client.post(
            "/auth/register/organization",
            data={
                "name": "Test Org",
                "username": "test-org",
                "email": "test@example.com",
                "password": "TestPass123!TestPwd",
            },
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 303)
