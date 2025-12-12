"""Opportunity and application schemas."""

from uuid import UUID

from app.core.base_schemas import BaseCreate, BaseOut, BaseUpdate
from app.core.types import LocationField, LongDescriptionField, OpportunityDescriptionField, TitleField
from app.db.models import ApplicationStatusType


class OpportunityCreate(BaseCreate):
    """Create an opportunity."""

    title: TitleField
    description: OpportunityDescriptionField
    location: LocationField
    organization_id: UUID


class OpportunityResponse(BaseOut):
    """Opportunity details."""

    title: str
    description: str
    location: str | None
    posted_by: UUID
    organization_id: UUID
    is_open: bool


class ApplicationCreate(BaseCreate):
    """Apply to an opportunity."""

    message: LongDescriptionField = None


class ApplicationResponse(BaseOut):
    """Application details."""

    opportunity_id: UUID
    volunteer_id: UUID
    status: ApplicationStatusType
    message: str | None


class ApplicationStatusUpdate(BaseUpdate):
    """Update application status."""

    status: ApplicationStatusType
