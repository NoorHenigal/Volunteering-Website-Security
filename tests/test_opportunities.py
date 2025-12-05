"""Opportunities tests."""

from uuid import UUID, uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext
from tests.fixtures.flows import FlowHelper

FAKE_UUID = str(uuid4())


class TestOpportunityAPI:
    """Test opportunity API endpoints."""

    @pytest.mark.anyio
    async def test_organization_can_create_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test that organization role can create an opportunity."""
        test_org = await ctx.organization()

        data = await api.created(
            "/opportunities",
            auth=test_org.admin,
            json={
                "title": "River Cleanup",
                "description": "Help clean up the river",
                "location": "Quayside",
                "organization_id": str(test_org.organization.id),
            },
        )

        assert data["title"] == "River Cleanup"
        assert data["description"] == "Help clean up the river"
        assert data["location"] == "Quayside"
        assert UUID(data["organization_id"]) == test_org.organization.id
        assert data["is_open"] is True

    @pytest.mark.anyio
    async def test_authenticated_user_can_list_opportunities(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test that authenticated users can list opportunities."""
        await ctx.opportunity()  # Create one first
        volunteer = await ctx.volunteer()
        data = await api.ok("GET", "/opportunities", auth=volunteer)
        assert "items" in data
        assert len(data["items"]) >= 1

    @pytest.mark.anyio
    async def test_unauthenticated_user_cannot_list_opportunities(self, api: APIHelper) -> None:
        """Test that unauthenticated users cannot list opportunities."""
        await api.unauthorized("GET", "/opportunities")

    @pytest.mark.anyio
    async def test_authenticated_user_can_get_single_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test that authenticated users can get a single opportunity."""
        test_opp = await ctx.opportunity()
        volunteer = await ctx.volunteer()
        data = await api.ok("GET", f"/opportunities/{test_opp.opportunity.id}", auth=volunteer)
        assert UUID(data["id"]) == test_opp.opportunity.id

    @pytest.mark.anyio
    async def test_create_opp_nonexistent_org_fails(
        self,
        api: APIHelper,
        flows: FlowHelper,
    ) -> None:
        """Test that creating opportunity with nonexistent organization fails."""
        org_user = await flows.create_user("organization")
        await api.not_found(
            "POST",
            "/opportunities",
            auth=org_user,
            json={
                "title": "Beach Cleanup",
                "description": "Help clean up the beach",
                "organization_id": FAKE_UUID,
            },
        )

    @pytest.mark.anyio
    async def test_get_nonexistent_opportunity_fails(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test that getting nonexistent opportunity fails."""
        volunteer = await ctx.volunteer()
        await api.not_found("GET", f"/opportunities/{FAKE_UUID}", auth=volunteer)


class TestOpportunityUI:
    """Test opportunity UI endpoints."""

    @pytest.mark.anyio
    async def test_unauthenticated_user_redirected_to_login(self, client: AsyncClient) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = await client.get("/opportunities", headers={"Accept": "text/html"}, follow_redirects=False)
        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert response.headers["location"] == "/auth/login"

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
        response = await client.get("/opportunities", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_200_OK
        assert b"Volunteering Opportunities" in response.content
