"""Business logic for organizations.

This service layer consolidates logic shared between API and UI handlers.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Organization
from app.db.repositories import OrganizationRepository, UserOrganizationRoleRepository
from app.organizations.schemas import OrganizationMemberResponse


class OrganizationService:
    """Service for organization-related business logic."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session."""
        self.db = db
        self._org_repo = OrganizationRepository(db)
        self._role_repo = UserOrganizationRoleRepository(db)

    async def list_all(self) -> list[Organization]:
        """Get all organizations."""
        return await self._org_repo.get_all()

    def _require_found(self, organization: Organization | None) -> Organization:
        """Require organization to exist or raise 404."""
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization:
        """Get organization by ID or raise 404."""
        return self._require_found(await self._org_repo.get_by_id(organization_id))

    async def get_by_id_with_opportunities(self, organization_id: UUID) -> Organization:
        """Get organization by ID with opportunities or raise 404."""
        return self._require_found(await self._org_repo.get_by_id_with_opportunities(organization_id))

    async def create(
        self,
        *,
        name: str,
        description: str | None,
        admin_user_id: UUID,
    ) -> Organization:
        """Create a new organization with the creator as admin.

        Args:
            name: Organization name
            description: Optional description
            admin_user_id: User ID to assign as admin

        Returns:
            Created Organization
        """
        return await self._org_repo.create_with_admin(name, description, admin_user_id)

    async def update(
        self,
        organization: Organization,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Organization:
        """Update an organization.

        Args:
            organization: Organization to update
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated Organization
        """
        if name is not None:
            organization.name = name
        if description is not None:
            organization.description = description

        return await self._org_repo.update(organization)

    async def get_members(self, organization_id: UUID) -> list[OrganizationMemberResponse]:
        """Get organization members with user details."""
        member_roles = await self._role_repo.get_members_with_users(organization_id)
        return [
            OrganizationMemberResponse(
                user_id=r.user.id,
                email=r.user.email,
                role=r.role,
            )
            for r in member_roles
        ]

    async def is_admin(self, user_id: UUID, organization_id: UUID) -> bool:
        """Check if user is admin of organization."""
        return await self._role_repo.is_organization_admin(user_id, organization_id)

    async def is_member(self, user_id: UUID, organization_id: UUID) -> bool:
        """Check if user is member of organization."""
        return await self._role_repo.is_organization_member(user_id, organization_id)

    async def require_admin(self, user_id: UUID, organization_id: UUID) -> None:
        """Require user to be admin of organization."""
        if not await self.is_admin(user_id, organization_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization admins can perform this action",
            )

    async def require_member(self, user_id: UUID, organization_id: UUID) -> None:
        """Require user to be member of organization."""
        if not await self.is_member(user_id, organization_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Must be organization member",
            )
