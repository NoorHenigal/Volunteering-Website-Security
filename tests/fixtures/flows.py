"""Reusable high-level flows for common test scenarios."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.api import APIHelper
from tests.fixtures.data import (
    ApplicationCreateFactory,
    AuthenticatedUser,
    OpportunityContext,
    OpportunityCreateFactory,
    OrganizationContext,
    OrganizationCreateFactory,
    RegisterSchemaFactory,
    RoleType,
    add_user_to_organization,
    get_user_from_db,
)


class FlowHelper:
    """Reusable flow operations for common test scenarios."""

    def __init__(self, api: APIHelper) -> None:
        """Initialize with APIHelper instance."""
        self.api = api

    async def create_user(self, role: RoleType = "volunteer") -> AuthenticatedUser:
        """Create and login a new volunteer user."""
        data = RegisterSchemaFactory.build()
        password = data.password.get_secret_value()

        form_data: dict[str, str] = {
            "email": data.email,
            "password": password,
            "first_name": data.first_name,
            "last_name": data.last_name,
            "username": data.username,
        }
        csrf_token = self.api.client.cookies.get("csrf_token")
        if csrf_token:
            form_data["csrf_token"] = csrf_token

        resp = await self.api.client.post(
            "/auth/register/volunteer",
            data=form_data,
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert resp.status_code in (200, 303), f"Registration failed: {resp.status_code}"

        access_token = resp.cookies.get("access_token")
        if not access_token:
            login_form: dict[str, str] = {"email": data.email, "password": password, "account_type": "volunteer"}
            csrf = self.api.client.cookies.get("csrf_token")
            if csrf:
                login_form["csrf_token"] = csrf
            login_resp = await self.api.client.post(
                "/auth/login",
                data=login_form,
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )
            assert login_resp.status_code in (200, 303), f"Login failed: {login_resp.status_code}"
            access_token = login_resp.cookies.get("access_token", "")

        return AuthenticatedUser(
            id=UUID(int=0),  # ID will be fetched from DB if needed
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            password=password,
            username=data.username,
            tokens={"access_token": access_token or ""},
            role=role,
        )

    async def apply(
        self,
        opp: OpportunityContext | UUID,
        volunteer: AuthenticatedUser,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Apply to an opportunity."""
        opp_id = opp.opportunity.id if isinstance(opp, OpportunityContext) else opp
        data = ApplicationCreateFactory.build()
        await self.api.created(
            f"/opportunities/{opp_id}/apply",
            auth=volunteer,
            data={"message": message or data.message or "I would like to volunteer!"},
        )
        return {"id": str(opp_id), "opportunity_id": str(opp_id), "status": "pending"}

    async def accept(
        self,
        app_id: str | UUID,
        admin: AuthenticatedUser,
    ) -> dict[str, Any]:
        """Accept an application."""
        await self.api.ok(
            "POST",
            f"/opportunities/{app_id}/applicants/{app_id}/accept",
            auth=admin,
        )
        return {"status": "accepted", "id": str(app_id)}

    async def reject(
        self,
        app_id: str | UUID,
        admin: AuthenticatedUser,
    ) -> dict[str, Any]:
        """Reject an application."""
        await self.api.ok(
            "POST",
            f"/opportunities/{app_id}/applicants/{app_id}/reject",
            auth=admin,
        )
        return {"status": "rejected", "id": str(app_id)}

    async def withdraw(
        self,
        app_id: str | UUID,
        volunteer: AuthenticatedUser,
    ) -> None:
        """Withdraw an application."""
        await self.api.ok(
            "POST",
            f"/applications/{app_id}/withdraw",
            auth=volunteer,
        )

    async def create_org(
        self,
        user: AuthenticatedUser,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create an organization."""
        data = OrganizationCreateFactory.build()
        org_name = name or data.name
        await self.api.created(
            "/organizations",
            auth=user,
            data={
                "name": org_name,
                "username": data.username,
                "description": description or data.description or "",
            },
        )
        return {"id": data.username, "name": org_name, "username": data.username}

    async def create_opp(
        self,
        user: AuthenticatedUser,
        org_id: str | UUID,
        title: str | None = None,
        description: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """Create an opportunity."""
        data = OpportunityCreateFactory.build()
        opp_title = title or data.title
        resp = await self.api.created(
            "/opportunities",
            auth=user,
            data={
                "title": opp_title,
                "description": description or data.description or "",
                "location": location or data.location or "",
                "organization_id": str(org_id),
            },
        )
        # Extract opportunity ID from redirect URL
        location_header = resp.headers.get("location", "")
        opp_id_match = re.search(r"/opportunities/([a-f0-9-]+)", location_header)
        opp_id = opp_id_match.group(1) if opp_id_match else str(org_id)
        return {"id": opp_id, "title": opp_title, "organization_id": str(org_id)}

    async def complete_application_flow(
        self,
        opp: OpportunityContext,
        volunteer: AuthenticatedUser,
        final_status: str = "accepted",
    ) -> dict[str, Any]:
        """Complete application flow: apply -> review -> update status."""
        app = await self.apply(opp, volunteer)
        opp_id = str(opp.opportunity.id)

        if final_status == "accepted":
            # Use the proper accept endpoint with opportunity and application IDs
            await self.api.ok(
                "POST",
                f"/opportunities/{opp_id}/applicants/{app['id']}/accept",
                auth=opp.organization.admin,
            )
            return {"status": "accepted", "id": app["id"]}
        if final_status == "rejected":
            await self.api.ok(
                "POST",
                f"/opportunities/{opp_id}/applicants/{app['id']}/reject",
                auth=opp.organization.admin,
            )
            return {"status": "rejected", "id": app["id"]}
        if final_status == "withdrawn":
            await self.withdraw(app["id"], volunteer)
            return app
        return app

    async def login_via_ui(
        self,
        email: str,
        password: str,
        account_type: str = "volunteer",
    ) -> None:
        """Login via UI form to set cookies."""
        await self.api.client.post(
            "/auth/login",
            data={"email": email, "password": password, "account_type": account_type},
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )

    async def add_member(
        self,
        db: AsyncSession,
        user: AuthenticatedUser,
        org: OrganizationContext | dict[str, Any],
        role: str = "member",
    ) -> None:
        """Add a user as member to an organization (DB operation for permission tests)."""
        org_id = org.organization.id if isinstance(org, OrganizationContext) else UUID(org["id"])
        db_user = await get_user_from_db(db, user.email)
        await add_user_to_organization(db, db_user.id, org_id, role=role)
