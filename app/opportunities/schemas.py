"""Data validation schemas for opportunities."""

from uuid import UUID

from app.core.base_schemas import BaseCreate, BaseOut, BaseUpdate
from app.core.types import LocationField, TitleField
from app.db.models import ApplicationStatusType


class OpportunityCreate(BaseCreate):
    """Opportunity creation data."""

    title: TitleField
    description: str
    location: LocationField
    organization_id: UUID


class OpportunityResponse(BaseOut):
    """Opportunity information response."""

    title: str
    description: str
    location: str | None
    posted_by: UUID
    organization_id: UUID
    is_open: bool


class ApplicationCreate(BaseCreate):
    """Application creation data."""

    message: str | None = None


class ApplicationResponse(BaseOut):
    """Application information response."""

    opportunity_id: UUID
    volunteer_id: UUID
    status: ApplicationStatusType
    message: str | None


class ApplicationStatusUpdate(BaseUpdate):
    """Application status update data."""

    status: ApplicationStatusType
