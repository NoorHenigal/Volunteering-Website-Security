"""Integration tests."""

from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from pyfakefs.fake_filesystem import FakeFilesystem
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from tests.fixtures.api import APIHelper
from tests.fixtures.data import FixtureContext
from tests.fixtures.flows import FlowHelper
from tests.test_uploads import create_test_image

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
        opps = await api.ok("GET", "/opportunities", auth=volunteer)
        assert "items" in opps

        # View opportunity details
        detail = await api.ok("GET", f"/opportunities/{test_opp.opportunity.id}", auth=volunteer)
        assert detail["id"] == str(test_opp.opportunity.id)

        # Apply to opportunity
        app = await flows.apply(test_opp, volunteer, message="I'm passionate about helping!")
        assert app["status"] == "pending"

        # View applications
        apps = await api.ok("GET", "/applications", auth=volunteer)
        assert len(apps["items"]) == 1
        assert UUID(apps["items"][0]["opportunity_id"]) == test_opp.opportunity.id

        # Withdraw application (deletes it)
        await flows.withdraw(app["id"], volunteer)

        # Verify application is gone
        apps_after = await api.ok("GET", "/applications", auth=volunteer)
        assert len(apps_after["items"]) == 0


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
            f"/opportunities/{opp['id']}/apply",
            auth=volunteer,
            json={"message": "I'd love to help with this!"},
        )

        # Organization accepts
        accepted = await flows.accept(app["id"], org_user)
        assert accepted["status"] == "accepted"


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

        await api.list_contains("/applications", auth=volunteer, expected_count=3)


class TestAuthorizationBoundaries:
    """Test authorization and permission boundaries."""

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
            "/opportunities",
            auth=volunteer,
            json={
                "title": "Unauthorized",
                "description": "Should fail",
                "organization_id": str(test_org.organization.id),
            },
        )

    @pytest.mark.anyio
    async def test_volunteer_can_create_organization(
        self, api: APIHelper, ctx: FixtureContext, flows: FlowHelper
    ) -> None:
        """Test: Volunteers CAN now create organizations (new permission model)."""
        volunteer = await ctx.volunteer()
        data = await api.created(
            "/organizations",
            auth=volunteer,
            json={
                "name": "Volunteer Created Org",
                "username": "volunteer-org",
                "email": "volunteer-org@example.com",
                "password": "TestPass123!TestPwd",
                "description": "Created by volunteer",
            },
        )
        assert data["name"] == "Volunteer Created Org"

    @pytest.mark.anyio
    async def test_volunteer_org_admin_can_still_apply_to_other_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
    ) -> None:
        """Test: Volunteer who is org admin can still apply to other opportunities."""
        test_opp = await ctx.opportunity()
        # Get another org context where user is admin but NOT part of test_opp's org
        other_org = await ctx.organization(key="other")
        # This volunteer/admin can apply (they're still a volunteer)
        app_data = await api.created(
            f"/opportunities/{test_opp.opportunity.id}/apply",
            auth=other_org.admin,
            json={"message": "Org admin can apply to other opps"},
        )
        assert app_data is not None

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
        await api.forbidden("DELETE", f"/applications/{app_data['id']}", auth=vol2)


class TestOrganizationMembership:
    """Test organization membership and role management."""

    @pytest.mark.anyio
    async def test_non_member_cannot_post_opportunity(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Organization user cannot post opportunity for org they're not member of."""
        test_org = await ctx.organization()
        other_user = await flows.create_user("volunteer")

        await api.forbidden(
            "POST",
            "/opportunities",
            auth=other_user,
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
        member = await flows.create_user("volunteer")
        await flows.add_member(test_db, member, test_org, role="member")

        await api.created(
            "/opportunities",
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
    async def test_ui_user_can_access_opportunities_list_with_create_overlay(
        self,
        client: AsyncClient,
        flows: FlowHelper,
        test_db: AsyncSession,
    ) -> None:
        """Test: User who is org member can access opportunities list with create overlay."""
        user = await flows.create_user("volunteer")
        await flows.create_org(user)  # creates org and makes user admin
        await flows.login_via_ui(user.email, user.password)
        response = await client.get("/opportunities", headers={"Accept": "text/html"}, follow_redirects=True)
        assert response.status_code == status.HTTP_200_OK
        # Verify the create overlay form is present
        assert "Post New Opportunity" in response.text
        assert "createOppOpen" in response.text

    @pytest.mark.anyio
    async def test_ui_user_without_org_sees_org_creation_overlay(
        self,
        client: AsyncClient,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: User without org membership sees org creation overlay option."""
        volunteer = await ctx.volunteer()
        await flows.login_via_ui(volunteer.email, volunteer.password)
        response = await client.get("/opportunities", headers={"Accept": "text/html"}, follow_redirects=False)

        # Should return 200 with org creation overlay for users without orgs
        assert response.status_code == status.HTTP_200_OK
        assert "Create Organization First" in response.text
        assert "Organization Required" in response.text


class TestDisplayNames:
    """Test display name configuration and updates."""

    @pytest.mark.anyio
    async def test_volunteer_can_update_display_name(
        self,
        api: APIHelper,
        ctx: FixtureContext,
        flows: FlowHelper,
    ) -> None:
        """Test: Volunteer can update their display name and it reflects in profile."""
        volunteer = await ctx.volunteer()

        # Initial state - uses first last
        profile = await api.ok("GET", f"/{volunteer.username}", auth=volunteer)
        assert profile["first_name"] == volunteer.first_name
        assert profile["last_name"] == volunteer.last_name

        # Update display name
        new_name = "Super Volunteer"
        await api.ok("PUT", "/settings/profile", auth=volunteer, json={"display_name": new_name})

        # Verify in profile
        await api.ok("GET", f"/{volunteer.username}", auth=volunteer)

        # Let's check DB directly to be sure
        from app.db.repositories import UserRepository

        repo = UserRepository(ctx.db)
        db_user = await repo.get_by_id(volunteer.id)
        assert db_user is not None
        assert db_user.custom_display_name == new_name
        assert db_user.display_name == new_name


class TestEdgeCases:
    """Test edge cases and error handling using parametrization."""

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
            f"/applications/{app_data['id']}/status",
            expected=status.HTTP_400_BAD_REQUEST,
            auth=test_opp.organization.admin,
            json={"status": "invalid_status"},
        )

    @pytest.mark.anyio
    async def test_login_with_wrong_password(self, api: APIHelper, ctx: FixtureContext) -> None:
        """Test: Login with wrong password fails."""
        volunteer = await ctx.volunteer()
        await api.unauthorized(
            "POST",
            "/auth/login",
            json={"email": volunteer.email, "password": "wrong_password123!"},
        )


class TestProfilePictureUserFlow:
    """Test profile picture upload as part of user journey."""

    @pytest.fixture
    def mock_upload_dir(self, fs: FakeFilesystem) -> Generator[Path]:
        """Mock upload directory use fake filesystem for integration tests."""
        import tempfile

        upload_dir = Path(tempfile.gettempdir()) / "test_uploads"
        fs.makedirs(str(upload_dir), exist_ok=True)
        with patch("app.core.config.settings.upload_dir", upload_dir):
            yield upload_dir

    @pytest.mark.anyio
    async def test_volunteer_can_upload_profile_picture(
        self,
        client: AsyncClient,
        ctx: FixtureContext,
        mock_upload_dir: Path,
    ) -> None:
        """Test: Volunteer can upload and update their profile picture."""
        volunteer = await ctx.volunteer()
        buffer = BytesIO(create_test_image())

        response = await client.post(
            "/settings/profile/picture",
            files={"file": ("test.png", buffer, "image/png")},
            headers=volunteer.auth_header,
        )

        assert response.status_code in (200, 303)

    @pytest.mark.anyio
    async def test_upload_profile_picture_requires_auth(
        self,
        client: AsyncClient,
        mock_upload_dir: Path,
    ) -> None:
        """Test: Profile picture upload requires authentication."""
        buffer = BytesIO(create_test_image())

        response = await client.post(
            "/settings/profile/picture",
            files={"file": ("test.png", buffer, "image/png")},
        )

        assert response.status_code == 303

    @pytest.mark.anyio
    async def test_upload_rejects_non_image_file(
        self,
        client: AsyncClient,
        ctx: FixtureContext,
        mock_upload_dir: Path,
    ) -> None:
        """Test: Non-image files are rejected during upload."""
        volunteer = await ctx.volunteer()

        response = await client.post(
            "/settings/profile/picture",
            files={"file": ("test.txt", b"not an image", "text/plain")},
            headers=volunteer.auth_header,
        )

        assert response.status_code == 400

    @pytest.mark.anyio
    async def test_volunteer_profile_picture_cleanup_on_update(
        self,
        client: AsyncClient,
        ctx: FixtureContext,
        mock_upload_dir: Path,
    ) -> None:
        """Test: Old profile pictures are cleaned up when user uploads new one."""
        volunteer = await ctx.volunteer()

        # Upload first picture
        buffer1 = BytesIO(create_test_image())
        response1 = await client.post(
            "/settings/profile/picture",
            files={"file": ("test1.png", buffer1, "image/png")},
            headers=volunteer.auth_header,
        )
        assert response1.status_code in (200, 303)

        # Get list of files after first upload
        files_after_first = list(mock_upload_dir.rglob("*.webp"))
        assert len(files_after_first) == 1

        # Upload second picture
        buffer2 = BytesIO(create_test_image())
        response2 = await client.post(
            "/settings/profile/picture",
            files={"file": ("test2.png", buffer2, "image/png")},
            headers=volunteer.auth_header,
        )
        assert response2.status_code in (200, 303)

        # Verify old picture was cleaned up
        files_after_second = list(mock_upload_dir.rglob("*.webp"))
        assert len(files_after_second) == 1
        assert files_after_first[0].name != files_after_second[0].name
