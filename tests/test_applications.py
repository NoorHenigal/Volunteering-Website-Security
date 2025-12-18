"""Applications tests."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application
from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext
from tests.fixtures.flows import FlowHelper


class TestApplication:
    """Test application endpoints."""

    @pytest.mark.anyio
    async def test_volunteer_can_apply_to_opportunity(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Volunteer can apply to open opportunity."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        response = await api.created(
            f"/opportunities/{test_opp.opportunity.id}/apply",
            auth=volunteer,
            data={"message": "I would love to help!"},
        )
        assert response.status_code in (200, 303)

    @pytest.mark.anyio
    async def test_volunteer_cannot_apply_twice(self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper) -> None:
        """Test: Volunteer cannot submit duplicate applications."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        await flows.apply(test_opp, volunteer)

        response = await api.conflict(
            "POST",
            f"/opportunities/{test_opp.opportunity.id}/apply",
            auth=volunteer,
            data={"message": "Second application"},
        )
        assert response.status_code in (400, 409)

    @pytest.mark.anyio
    async def test_list_volunteer_applications(self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper) -> None:
        """Test: Volunteer can view their applications page."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        await flows.apply(test_opp, volunteer)

        response = await api.ok("GET", "/applications", auth=volunteer)
        assert response.status_code == 200
        assert "My Applications" in response.text

    @pytest.mark.anyio
    async def test_volunteer_can_withdraw_application(
        self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper, test_db: AsyncSession
    ) -> None:
        """Test: Volunteer can withdraw their application."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        await flows.apply(test_opp, volunteer)

        result = await test_db.execute(select(Application).where(Application.opportunity_id == test_opp.opportunity.id))
        application = result.scalar_one()

        response = await api.ok(
            "POST",
            f"/applications/{application.id}/withdraw",
            auth=volunteer,
        )
        assert response.status_code in (200, 303)

    @pytest.mark.anyio
    async def test_org_admin_can_accept_application(
        self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper, test_db: AsyncSession
    ) -> None:
        """Test: Organization admin can accept applications."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        await flows.apply(test_opp, volunteer)

        result = await test_db.execute(select(Application).where(Application.opportunity_id == test_opp.opportunity.id))
        application = result.scalar_one()

        response = await api.ok(
            "POST",
            f"/opportunities/{test_opp.opportunity.id}/applicants/{application.id}/accept",
            auth=test_opp.organization.admin,
        )
        assert response.status_code in (200, 303)

    @pytest.mark.anyio
    async def test_non_admin_cannot_update_application_status(
        self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper, test_db: AsyncSession
    ) -> None:
        """Test: Non-admin cannot update application status."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        await flows.apply(test_opp, volunteer)
        non_admin = await flows.create_user("organization")

        result = await test_db.execute(select(Application).where(Application.opportunity_id == test_opp.opportunity.id))
        application = result.scalar_one()

        response = await api.forbidden(
            "POST",
            f"/opportunities/{test_opp.opportunity.id}/applicants/{application.id}/accept",
            auth=non_admin,
        )
        assert response.status_code == 403

    @pytest.mark.anyio
    async def test_cannot_apply_to_closed_opportunity(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Volunteer cannot apply to closed opportunity."""
        volunteer = await ctx.volunteer()
        closed_opp = await ctx.opportunity(key="closed", is_open=False)

        response = await api.bad_request(
            "POST",
            f"/opportunities/{closed_opp.opportunity.id}/apply",
            auth=volunteer,
            data={"message": "Application"},
        )
        assert response.status_code == 400
