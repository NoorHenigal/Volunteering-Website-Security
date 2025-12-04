"""Reusable high-level flows for common test scenarios."""

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
        """Create and login a new user (self-contained, no conftest dependency)."""
        data = RegisterSchemaFactory.build(role=role)
        resp = await self.api.client.post(
            "/api/auth/register",
            json={
                "email": data.email,
                "password": data.password,
                "role": role,
                "first_name": data.first_name,
                "last_name": data.last_name,
                "username": data.username,
            },
        )
        assert 200 <= resp.status_code < 300, f"Registration failed: {resp.text}"

        tokens_resp = await self.api.client.post(
            "/api/auth/login",
            json={"email": data.email, "password": data.password},
        )
        assert tokens_resp.status_code == 200, f"Login failed: {tokens_resp.text}"
        tokens: dict[str, str] = tokens_resp.json()

        return AuthenticatedUser(email=data.email, password=data.password, tokens=tokens, role=role)

    async def apply(
        self,
        opp: OpportunityContext | UUID,
        volunteer: AuthenticatedUser,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Apply to an opportunity."""
        opp_id = opp.opportunity.id if isinstance(opp, OpportunityContext) else opp
        data = ApplicationCreateFactory.build()
        return await self.api.created(
            f"/api/opportunities/{opp_id}/apply",
            auth=volunteer,
            json={"message": message or data.message or "I would like to volunteer!"},
        )

    async def accept(
        self,
        app_id: str | UUID,
        admin: AuthenticatedUser,
    ) -> dict[str, Any]:
        """Accept an application."""
        return await self.api.ok(
            "PUT",
            f"/api/applications/{app_id}/status",
            auth=admin,
            json={"status": "accepted"},
        )

    async def reject(
        self,
        app_id: str | UUID,
        admin: AuthenticatedUser,
    ) -> dict[str, Any]:
        """Reject an application."""
        return await self.api.ok(
            "PUT",
            f"/api/applications/{app_id}/status",
            auth=admin,
            json={"status": "rejected"},
        )

    async def withdraw(
        self,
        app_id: str | UUID,
        volunteer: AuthenticatedUser,
    ) -> None:
        """Withdraw an application (deletes it)."""
        await self.api.no_content(
            "DELETE",
            f"/api/applications/{app_id}/withdraw",
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
        return await self.api.created(
            "/api/organizations",
            auth=user,
            json={
                "name": name or data.name,
                "description": description or data.description,
            },
        )

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
        return await self.api.created(
            "/api/opportunities",
            auth=user,
            json={
                "title": title or data.title,
                "description": description or data.description,
                "location": location or data.location,
                "organization_id": str(org_id),
            },
        )

    async def complete_application_flow(
        self,
        opp: OpportunityContext,
        volunteer: AuthenticatedUser,
        final_status: str = "accepted",
    ) -> dict[str, Any]:
        """Complete application flow: apply -> review -> update status."""
        app = await self.apply(opp, volunteer)

        if final_status == "accepted":
            return await self.accept(app["id"], opp.organization.admin)
        if final_status == "rejected":
            return await self.reject(app["id"], opp.organization.admin)
        if final_status == "withdrawn":
            await self.withdraw(app["id"], volunteer)
            return app
        return app

    async def login_via_ui(
        self,
        email: str,
        password: str,
    ) -> None:
        """Login via UI form to set cookies."""
        await self.api.client.post(
            "/auth/login",
            data={"email": email, "password": password},
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
