"""Opportunities tests."""

from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext
from tests.fixtures.flows import FlowHelper

FAKE_UUID = str(uuid4())


class TestOpportunityUI:
    """Test opportunity endpoints."""

    @pytest.mark.anyio
    async def test_organization_can_create_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test that organization role can create an opportunity."""
        test_org = await ctx.organization()

        response = await api.created(
            "/opportunities",
            auth=test_org.admin,
            data={
                "title": "River Cleanup",
                "description": "Help clean up the river",
                "location": "Quayside",
                "organization_id": str(test_org.organization.id),
            },
        )
        assert response.status_code in (200, 303)

    @pytest.mark.anyio
    async def test_authenticated_user_can_list_opportunities(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test that authenticated users can list opportunities."""
        await ctx.opportunity()  # Create one first
        volunteer = await ctx.volunteer()
        response = await api.ok("GET", "/opportunities", auth=volunteer)
        assert response.status_code == 200
        assert "Volunteering Opportunities" in response.text or "opportunities" in response.text.lower()

    @pytest.mark.anyio
    async def test_unauthenticated_user_cannot_list_opportunities(self, api: APIHelper) -> None:
        """Test that unauthenticated users get 401."""
        response = await api.unauthorized("GET", "/opportunities")
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_authenticated_user_can_get_single_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test that authenticated users can view a single opportunity."""
        test_opp = await ctx.opportunity()
        volunteer = await ctx.volunteer()
        response = await api.ok("GET", f"/opportunities/{test_opp.opportunity.id}", auth=volunteer)
        assert response.status_code == 200
        assert test_opp.opportunity.title in response.text

    @pytest.mark.anyio
    async def test_create_opp_nonexistent_org_fails(
        self,
        api: APIHelper,
        flows: FlowHelper,
    ) -> None:
        """Test that creating opportunity with nonexistent organization fails."""
        org_user = await flows.create_user("organization")
        response = await api.not_found(
            "POST",
            "/opportunities",
            auth=org_user,
            data={
                "title": "Beach Cleanup",
                "description": "Help clean up the beach",
                "organization_id": FAKE_UUID,
            },
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_get_nonexistent_opportunity_fails(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test that getting nonexistent opportunity returns 404."""
        volunteer = await ctx.volunteer()
        await api.not_found("GET", f"/opportunities/{FAKE_UUID}", auth=volunteer)


class TestOpportunityUIPages:
    """Test opportunity UI page rendering."""

    @pytest.mark.anyio
    async def test_unauthenticated_user_gets_401(self, client: AsyncClient) -> None:
        """Test that unauthenticated users get 401."""
        response = await client.get("/opportunities", headers={"Accept": "text/html"}, follow_redirects=False)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.anyio
    async def test_authenticated_user_can_view_list_page(
        self,
        client: AsyncClient,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test that authenticated users can view the list page."""
        volunteer = await ctx.volunteer()
        await flows.login_via_ui(volunteer.email, volunteer.password)
        response = await client.get("/opportunities", headers={"Accept": "text/html"}, follow_redirects=True)
        # After login and redirect, should get the content
        assert response.status_code == status.HTTP_200_OK
