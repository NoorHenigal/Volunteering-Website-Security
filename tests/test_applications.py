"""Applications tests."""

import pytest

from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext
from tests.fixtures.flows import FlowHelper


class TestApplicationAPI:
    """Test application API endpoints."""

    @pytest.mark.anyio
    async def test_volunteer_can_apply_to_opportunity(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Volunteer can apply to open opportunity."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        data = await api.created(
            f"/api/opportunities/{test_opp.opportunity.id}/apply",
            auth=volunteer,
            json={"message": "I would love to help!"},
        )

        assert data["status"] == "pending"
        assert data["message"] == "I would love to help!"

    @pytest.mark.anyio
    async def test_volunteer_cannot_apply_twice(self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper) -> None:
        """Test: Volunteer cannot submit duplicate applications."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        await flows.apply(test_opp, volunteer)

        await api.bad_request(
            "POST",
            f"/api/opportunities/{test_opp.opportunity.id}/apply",
            auth=volunteer,
            json={"message": "Second application"},
        )

    @pytest.mark.anyio
    async def test_list_volunteer_applications(self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper) -> None:
        """Test: Volunteer can list their applications."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        await flows.apply(test_opp, volunteer)

        await api.list_contains("/api/applications", auth=volunteer, expected_count=1)

    @pytest.mark.anyio
    async def test_volunteer_can_withdraw_application(
        self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper
    ) -> None:
        """Test: Volunteer can withdraw their application."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        app_data = await flows.apply(test_opp, volunteer)

        data = await api.ok("PUT", f"/api/applications/{app_data['id']}/withdraw", auth=volunteer)
        assert data["status"] == "withdrawn"

    @pytest.mark.anyio
    async def test_org_admin_can_update_application_status(
        self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper
    ) -> None:
        """Test: Organization admin can accept/reject applications."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        app_data = await flows.apply(test_opp, volunteer)

        data = await flows.accept(app_data["id"], test_opp.organization.admin)
        assert data["status"] == "accepted"

    @pytest.mark.anyio
    async def test_non_admin_cannot_update_application_status(
        self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper
    ) -> None:
        """Test: Non-admin cannot update application status."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        app_data = await flows.apply(test_opp, volunteer)
        non_admin = await flows.create_user("organization")

        await api.forbidden(
            "PUT",
            f"/api/applications/{app_data['id']}/status",
            auth=non_admin,
            json={"status": "accepted"},
        )

    @pytest.mark.anyio
    async def test_cannot_apply_to_closed_opportunity(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Volunteer cannot apply to closed opportunity."""
        volunteer = await ctx.volunteer()
        closed_opp = await ctx.opportunity(key="closed", is_open=False)

        await api.bad_request(
            "POST",
            f"/api/opportunities/{closed_opp.opportunity.id}/apply",
            auth=volunteer,
            json={"message": "Application"},
        )
