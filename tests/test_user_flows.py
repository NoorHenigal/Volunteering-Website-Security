"""Integration tests."""

from uuid import UUID, uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext
from tests.fixtures.flows import FlowHelper

FAKE_UUID = str(uuid4())


class TestVolunteerJourney:
    """Test complete volunteer user journey from registration to application."""

    @pytest.mark.anyio
    async def test_volunteer_complete_journey(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Volunteer browses opportunities, applies, and tracks applications."""
        test_opp = await ctx.opportunity()
        volunteer = await ctx.volunteer()

        # List opportunities
        opps = await api.ok("GET", "/api/opportunities", auth=volunteer)
        assert "items" in opps

        # View opportunity details
        detail = await api.ok("GET", f"/api/opportunities/{test_opp.opportunity.id}", auth=volunteer)
        assert detail["id"] == str(test_opp.opportunity.id)

        # Apply to opportunity
        app = await flows.apply(test_opp, volunteer, message="I'm passionate about helping!")
        assert app["status"] == "pending"

        # View applications
        apps = await api.ok("GET", "/api/applications", auth=volunteer)
        assert len(apps["items"]) == 1
        assert UUID(apps["items"][0]["opportunity_id"]) == test_opp.opportunity.id

        # Withdraw application
        withdrawn = await flows.withdraw(app["id"], volunteer)
        assert withdrawn["status"] == "withdrawn"


class TestOrganizationJourney:
    """Test complete organization user journey from setup to managing applications."""

    @pytest.mark.anyio
    async def test_organization_complete_journey(self, api: APIHelper, flows: FlowHelper) -> None:
        """Test: Organization creates org, posts opportunity, reviews and accepts applications."""
        org_user = await flows.create_user("organization")

        # Create organization
        org = await flows.create_org(
            org_user, name="Sustainability Society", description="Student-led sustainability projects"
        )

        # Post opportunity
        opp = await flows.create_opp(
            org_user,
            org["id"],
            title="Campus Tree Planting",
            description="Help us plant trees around campus",
            location="Campus Green",
        )

        # Volunteer applies
        volunteer = await flows.create_user("volunteer")
        app = await api.created(
            f"/api/opportunities/{opp['id']}/apply",
            auth=volunteer,
            json={"message": "I'd love to help with this!"},
        )

        # Organization accepts
        accepted = await flows.accept(app["id"], org_user)
        assert accepted["status"] == "accepted"

    @pytest.mark.anyio
    async def test_organization_can_reject_application(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Organization can reject volunteer applications."""
        test_opp = await ctx.opportunity()
        volunteer = await ctx.volunteer()

        app_data = await flows.apply(test_opp, volunteer)
        rejected = await flows.reject(app_data["id"], test_opp.organization.admin)
        assert rejected["status"] == "rejected"

    @pytest.mark.anyio
    async def test_organization_can_update_details(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Organization admin can update organization details."""
        test_org = await ctx.organization()
        updated = await api.ok(
            "PUT",
            f"/api/organizations/{test_org.organization.id}",
            auth=test_org.admin,
            json={"name": "Updated Name", "description": "Updated description"},
        )
        assert updated["name"] == "Updated Name"


class TestMultiUserScenarios:
    """Test scenarios involving multiple users interacting."""

    @pytest.mark.anyio
    async def test_multiple_volunteers_apply_to_same_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Multiple volunteers can apply to the same opportunity."""
        test_opp = await ctx.opportunity()
        volunteers = await ctx.create_volunteers(3)

        for i, vol in enumerate(volunteers):
            await flows.apply(test_opp, vol, message=f"Volunteer {i + 1} applying")

    @pytest.mark.anyio
    async def test_volunteer_applies_to_multiple_opportunities(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Volunteer can apply to multiple different opportunities."""
        volunteer = await ctx.volunteer()
        org = await ctx.organization()
        opportunities = await ctx.create_opportunities(org, 3)

        for i, opp in enumerate(opportunities):
            await flows.apply(opp.id, volunteer, message=f"Applying to opportunity {i + 1}")

        await api.list_contains("/api/applications", auth=volunteer, expected_count=3)

    @pytest.mark.anyio
    async def test_non_admin_cannot_manage_applications(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Non-admin organization members cannot accept/reject applications."""
        volunteer = await ctx.volunteer()
        test_opp = await ctx.opportunity()

        app_data = await flows.apply(test_opp, volunteer)
        other_org_user = await flows.create_user("organization")

        await api.forbidden(
            "PUT",
            f"/api/applications/{app_data['id']}/status",
            auth=other_org_user,
            json={"status": "accepted"},
        )


class TestAuthorizationBoundaries:
    """Test authorization and permission boundaries."""

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("endpoint", "method"),
        [
            ("/api/opportunities", "GET"),
            ("/api/organizations", "GET"),
            ("/api/applications", "GET"),
        ],
    )
    async def test_unauthenticated_access_denied(self, api: APIHelper, endpoint: str, method: str) -> None:
        """Test: Unauthenticated users cannot access protected endpoints."""
        await api.unauthorized(method, endpoint)

    @pytest.mark.anyio
    async def test_volunteer_cannot_create_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test: Volunteers cannot create opportunities."""
        test_org = await ctx.organization()
        volunteer = await ctx.volunteer()
        await api.forbidden(
            "POST",
            "/api/opportunities",
            auth=volunteer,
            json={
                "title": "Unauthorized",
                "description": "Should fail",
                "organization_id": str(test_org.organization.id),
            },
        )

    @pytest.mark.anyio
    async def test_volunteer_cannot_create_organization(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Volunteers cannot create organizations."""
        volunteer = await ctx.volunteer()
        await api.forbidden(
            "POST",
            "/api/organizations",
            auth=volunteer,
            json={"name": "Unauthorized Org", "description": "Should fail"},
        )

    @pytest.mark.anyio
    async def test_organization_cannot_apply_to_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test: Organization users cannot apply to opportunities."""
        test_opp = await ctx.opportunity()
        org = await ctx.organization(key="other")
        await api.forbidden(
            "POST",
            f"/api/opportunities/{test_opp.opportunity.id}/apply",
            auth=org.admin,
            json={"message": "Orgs can't apply"},
        )

    @pytest.mark.anyio
    async def test_volunteer_cannot_withdraw_others_application(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Volunteers cannot withdraw other volunteers' applications."""
        test_opp = await ctx.opportunity()
        vol1 = await ctx.volunteer(key="vol1")
        app_data = await flows.apply(test_opp, vol1)

        vol2 = await ctx.volunteer(key="vol2")
        await api.forbidden("PUT", f"/api/applications/{app_data['id']}/withdraw", auth=vol2)


class TestOrganizationMembership:
    """Test organization membership and role management."""

    @pytest.mark.anyio
    async def test_org_creator_becomes_admin(self, api: APIHelper, flows: FlowHelper) -> None:
        """Test: User who creates organization automatically becomes admin."""
        org_user = await flows.create_user("organization")
        org = await flows.create_org(org_user, name="New Org", description="Test")

        detail = await api.ok("GET", f"/api/organizations/{org['id']}", auth=org_user)
        assert len(detail["members"]) == 1
        assert detail["members"][0]["email"] == org_user.email
        assert detail["members"][0]["role"] == "admin"

    @pytest.mark.anyio
    async def test_non_member_cannot_post_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Organization user cannot post opportunity for org they're not member of."""
        test_org = await ctx.organization()
        other_org_user = await flows.create_user("organization")

        await api.forbidden(
            "POST",
            "/api/opportunities",
            auth=other_org_user,
            json={
                "title": "Unauthorized Post",
                "description": "Should fail",
                "organization_id": str(test_org.organization.id),
            },
        )

    @pytest.mark.anyio
    async def test_member_can_post_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        test_db: AsyncSession,
        flows: FlowHelper,
    ) -> None:
        """Test: Organization member can post opportunity for their org."""
        test_org = await ctx.organization()
        member = await flows.create_user("organization")
        await flows.add_member(test_db, member, test_org, role="member")

        await api.created(
            "/api/opportunities",
            auth=member,
            json={
                "title": "Member Posted Opportunity",
                "description": "Posted by member",
                "organization_id": str(test_org.organization.id),
            },
        )


class TestUIFlows:
    """Test UI-based user flows with cookie authentication."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("page", ["/opp/list", "/org/list"])
    async def test_ui_unauthenticated_redirects_to_login(self, client: AsyncClient, page: str) -> None:
        """Test: Unauthenticated UI access redirects to login."""
        response = await client.get(page, follow_redirects=False)
        assert response.status_code == status.HTTP_303_SEE_OTHER
        assert response.headers["location"] == "/auth/login"

    @pytest.mark.anyio
    async def test_ui_login_and_browse_opportunities(
        self,
        client: AsyncClient,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: User can login via UI and browse opportunities."""
        await ctx.opportunity()  # Create one first
        volunteer = await ctx.volunteer()
        await flows.login_via_ui(volunteer.email, volunteer.password)
        response = await client.get("/opp/list", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.anyio
    async def test_ui_organization_can_access_create_form(
        self,
        client: AsyncClient,
        flows: FlowHelper,
    ) -> None:
        """Test: Organization user can access opportunity creation form."""
        org_user = await flows.create_user("organization")
        await flows.login_via_ui(org_user.email, org_user.password)
        response = await client.get("/opp/new", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_200_OK
        assert b"Create" in response.content

    @pytest.mark.anyio
    async def test_ui_volunteer_cannot_access_create_form(
        self,
        client: AsyncClient,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Volunteer cannot access opportunity creation form."""
        volunteer = await ctx.volunteer()
        await flows.login_via_ui(volunteer.email, volunteer.password)
        response = await client.get("/opp/new", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestEdgeCases:
    """Test edge cases and error handling using parametrization."""

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        ("endpoint", "method"),
        [
            (f"/api/opportunities/{FAKE_UUID}", "GET"),
            (f"/api/organizations/{FAKE_UUID}", "GET"),
            (f"/api/opportunities/{FAKE_UUID}/apply", "POST"),
        ],
        ids=["opportunity-get", "organization-get", "opportunity-apply"],
    )
    async def test_nonexistent_resource_returns_404(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        endpoint: str,
        method: str,
    ) -> None:
        """Test: Accessing nonexistent resources returns 404."""
        volunteer = await ctx.volunteer()
        json_data = {"message": "Test"} if method == "POST" else None
        await api.not_found(method, endpoint, auth=volunteer, json=json_data)

    @pytest.mark.anyio
    async def test_create_opportunity_for_nonexistent_org(
        self,
        api: APIHelper,
        flows: FlowHelper,
    ) -> None:
        """Test: Creating opportunity for nonexistent org returns 404."""
        org_user = await flows.create_user("organization")
        await api.not_found(
            "POST",
            "/api/opportunities",
            auth=org_user,
            json={"title": "Test", "description": "Test", "organization_id": FAKE_UUID},
        )

    @pytest.mark.anyio
    async def test_invalid_application_status_update(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Invalid status value is rejected."""
        test_opp = await ctx.opportunity()
        volunteer = await ctx.volunteer()
        app_data = await flows.apply(test_opp, volunteer)
        await api(
            "PUT",
            f"/api/applications/{app_data['id']}/status",
            expected=status.HTTP_422_UNPROCESSABLE_CONTENT,
            auth=test_opp.organization.admin,
            json={"status": "invalid_status"},
        )

    @pytest.mark.anyio
    async def test_login_with_wrong_password(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Login with wrong password fails."""
        volunteer = await ctx.volunteer()
        await api.unauthorized(
            "POST",
            "/api/auth/login",
            json={"email": volunteer.email, "password": "wrong_password123!"},
        )
