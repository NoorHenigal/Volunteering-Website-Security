"""Business logic for opportunities and applications.

This service layer consolidates logic shared between API and UI handlers.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import conflict, forbid
from app.core.service import BaseService
from app.db.models import Application, Opportunity, Organization, User
from app.db.repositories import (
    ApplicationRepository,
    OpportunityRepository,
    OrganizationRepository,
    UserOrganizationRoleRepository,
)


class OpportunityService(BaseService):
    """Service for opportunity-related business logic."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session."""
        super().__init__(db)
        self._opp_repo = OpportunityRepository(db)
        self._org_repo = OrganizationRepository(db)
        self._role_repo = UserOrganizationRoleRepository(db)

    async def list_open(self) -> list[Opportunity]:
        """Get all open opportunities."""
        return await self._opp_repo.get_all_open()

    async def get_by_id(self, opportunity_id: UUID) -> Opportunity:
        """Get opportunity by ID or raise 404."""
        return await self.get_or_404(self._opp_repo, opportunity_id, "Opportunity not found")

    async def create(
        self,
        *,
        title: str,
        description: str,
        organization_id: UUID,
        posted_by: UUID,
        location: str | None = None,
    ) -> Opportunity:
        """Create a new opportunity.

        Args:
            title: Opportunity title
            description: Opportunity description
            organization_id: Organization ID
            posted_by: User ID of the poster
            location: Optional location

        Returns:
            Created Opportunity

        Raises:
            HTTPException: If organization not found
        """
        # Verify organization exists
        if not await self._org_repo.get_by_id(organization_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        opportunity = Opportunity(
            title=title,
            description=description,
            posted_by=posted_by,
            organization_id=organization_id,
            location=location,
        )
        return await self._opp_repo.create(opportunity)

    async def get_user_organizations(self, user_id: UUID) -> list[Organization]:
        """Get organizations where user is a member."""
        user_org_roles = await self._role_repo.get_user_organizations(user_id)
        organizations = []
        for role in user_org_roles:
            org = await self._org_repo.get_by_id(role.organization_id)
            if org:
                organizations.append(org)
        return organizations


class ApplicationService(BaseService):
    """Service for application-related business logic."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session."""
        super().__init__(db)
        self._app_repo = ApplicationRepository(db)
        self._opp_repo = OpportunityRepository(db)

    async def check_already_applied(self, user_id: UUID, opportunity_id: UUID) -> Application | None:
        """Check if user has already applied to an opportunity."""
        return await self._app_repo.get_by_volunteer_and_opportunity(user_id, opportunity_id)

    async def require_not_applied(self, user_id: UUID, opportunity_id: UUID) -> None:
        """Raise error if user has already applied."""
        existing = await self.check_already_applied(user_id, opportunity_id)
        conflict(existing is not None, "You have already applied to this opportunity")

    async def apply(
        self,
        *,
        opportunity_id: UUID,
        volunteer_id: UUID,
        message: str | None = None,
    ) -> Application:
        """Apply to an opportunity.

        Args:
            opportunity_id: Opportunity to apply to
            volunteer_id: Volunteer user ID
            message: Optional application message

        Returns:
            Created Application

        Raises:
            HTTPException: If opportunity not found, closed, or already applied
        """
        # Verify opportunity exists and is open
        opportunity = await self.get_or_404(self._opp_repo, opportunity_id, "Opportunity not found")

        if not opportunity.is_open:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This opportunity is no longer accepting applications",
            )

        # Check if already applied
        await self.require_not_applied(volunteer_id, opportunity_id)

        # Create application
        application = Application(
            opportunity_id=opportunity_id,
            volunteer_id=volunteer_id,
            message=message,
        )
        return await self._app_repo.create(application)

    async def get_by_volunteer(self, volunteer_id: UUID) -> list[Application]:
        """Get all applications for a volunteer."""
        return await self._app_repo.get_by_volunteer(volunteer_id)

    async def get_by_volunteer_with_opportunity(self, volunteer_id: UUID) -> list[Application]:
        """Get all applications for a volunteer with opportunity details."""
        return await self._app_repo.get_by_volunteer_with_opportunity(volunteer_id)

    async def get_by_id(self, application_id: UUID) -> Application:
        """Get application by ID or raise 404."""
        application = await self._app_repo.get_by_id(application_id)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found",
            )
        return application

    async def update_status(self, application: Application, new_status: str) -> Application:
        """Update application status."""
        return await self._app_repo.update_status(application, new_status)

    async def withdraw(self, application_id: UUID, user: User) -> Application:
        """Withdraw an application (volunteers only).

        Args:
            application_id: Application to withdraw
            user: User attempting to withdraw

        Returns:
            Updated Application

        Raises:
            HTTPException: If not found or not owner
        """
        application = await self.get_by_id(application_id)

        forbid(application.volunteer_id != user.id, "You can only withdraw your own applications")

        return await self._app_repo.update_status(application, "withdrawn")

    async def get_by_opportunity_with_volunteer(self, opportunity_id: UUID) -> list[Application]:
        """Get all applications for an opportunity with volunteer details."""
        return await self._app_repo.get_by_opportunity_with_volunteer(opportunity_id)
