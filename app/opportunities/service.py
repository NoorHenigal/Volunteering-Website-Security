"""Opportunity and application business logic."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import conflict, forbid, require
from app.core.service import BaseService
from app.core.services.encryption import encrypt_field
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

    async def list_open(self, page: int = 1, limit: int = 100) -> tuple[list[Opportunity], int]:
        """Get all open opportunities with pagination."""
        skip = (page - 1) * limit
        items = await self._opp_repo.get_all_open(skip=skip, limit=limit)
        total = await self._opp_repo.count_open()
        return items, total

    async def get_by_id(self, opportunity_id: UUID) -> Opportunity:
        """Get opportunity by ID or raise 404."""
        opp = await self._opp_repo.get_by_id_with_organization(opportunity_id)
        return require(opp, "Opportunity not found")

    async def get_by_id_including_deleted(self, opportunity_id: UUID) -> Opportunity:
        """Get opportunity by ID including soft-deleted opportunities."""
        opp = await self._opp_repo.get_by_id(opportunity_id, include_deleted=True)
        return require(opp, "Opportunity not found")

    async def create(
        self,
        *,
        title: str,
        description: str,
        organization_id: UUID,
        posted_by: UUID,
        location: str | None = None,
    ) -> Opportunity:
        """Create a new opportunity."""
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

    async def soft_delete(self, opportunity_id: UUID) -> None:
        """Soft-delete an opportunity and withdraw pending applications."""
        opportunity = await self.get_by_id_including_deleted(opportunity_id)

        if opportunity.deleted_at is None:
            opportunity.deleted_at = datetime.now(UTC)
        opportunity.is_open = False
        await self._opp_repo.update(opportunity)

        await self.db.execute(
            update(Application)
            .where(
                Application.opportunity_id == opportunity_id,
                Application.status == "pending",
            )
            .values(status="withdrawn")
        )
        await self.db.flush()

    async def get_user_organizations(self, user_id: UUID) -> list[Organization]:
        """Get organizations where user is a member."""
        roles = await self._role_repo.get_user_organizations_with_org(user_id)
        return [r.organization for r in roles]

    async def update_banner(self, opportunity_id: UUID, filename: str) -> Opportunity:
        """Update opportunity banner."""
        opportunity = await self.get_by_id(opportunity_id)
        # Verify user is admin of organization (simple check for now, can be improved)
        # TODO In a real app we'd check permissions properly  # noqa: FIX002, TD002, TD003, TD004

        opportunity.banner = filename
        return await self._opp_repo.update(opportunity)


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
        """Apply to an opportunity."""
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
            message_ciphertext=encrypt_field(message),
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

    async def withdraw(self, application_id: UUID, user: User) -> None:
        """Withdraw an application (volunteers only)."""
        application = await self.get_by_id(application_id)

        forbid(application.volunteer_id != user.id, "You can only withdraw your own applications")

        await self._app_repo.delete(application)

    async def get_by_opportunity_with_volunteer(self, opportunity_id: UUID) -> list[Application]:
        """Get all applications for an opportunity with volunteer details."""
        return await self._app_repo.get_by_opportunity_with_volunteer(opportunity_id)
