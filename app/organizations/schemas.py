"""Organization schemas."""

from uuid import UUID

from pydantic import Field

from app.core.base_schemas import BaseCreate, BaseOut, BaseUpdate, StrictModel
from app.core.types import DescriptionField, NameField


class OrganizationCreate(BaseCreate):
    """Create an organization."""

    name: NameField
    username: str = Field(min_length=3, pattern=r"^[a-zA-Z0-9_-]+$")
    description: DescriptionField


class OrganizationUpdate(BaseUpdate):
    """Update an organization."""

    name: NameField | None = None
    description: DescriptionField


class OrganizationResponse(BaseOut):
    """Organization details."""

    name: str
    username: str
    description: str | None


class OrganizationMemberResponse(StrictModel):
    """Organization member with role."""

    user_id: UUID
    email: str
    username: str
    first_name: str | None = None
    last_name: str | None = None
    user_role: str  # "volunteer" or "organization" - organization users are "ghost" users
    role: str  # "admin" or "member" within the organization

    @property
    def display_name(self) -> str:
        """Get display name from first/last name or username."""
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.username

    @property
    def is_visible(self) -> bool:
        """Whether this member should be visible on public org page.

        Ghost users (user_role='organization') should never be shown.
        """
        return self.user_role != "organization"


class OrganizationDetailResponse(BaseOut):
    """Organization with members list."""

    name: str
    description: str | None
    members: list[OrganizationMemberResponse]
