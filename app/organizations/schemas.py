"""Data validation schemas for organizations."""

from uuid import UUID

from app.core.base_schemas import BaseCreate, BaseOut, BaseUpdate, StrictModel
from app.core.types import DescriptionField, NameField


class OrganizationCreate(BaseCreate):
    """Organization creation data."""

    name: NameField
    description: DescriptionField


class OrganizationUpdate(BaseUpdate):
    """Organization update data."""

    name: NameField | None = None
    description: DescriptionField


class OrganizationResponse(BaseOut):
    """Organization information response."""

    name: str
    description: str | None


class OrganizationMemberResponse(StrictModel):
    """Organization member information."""

    user_id: UUID
    email: str
    username: str
    first_name: str | None = None
    last_name: str | None = None
    role: str


class OrganizationDetailResponse(BaseOut):
    """Detailed organization information with members."""

    name: str
    description: str | None
    members: list[OrganizationMemberResponse]
