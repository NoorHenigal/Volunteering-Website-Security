"""Service dependency factories for FastAPI."""

from typing import Annotated

from fastapi import Depends

from app.core.context import RequestContext, get_context
from app.core.services.images import ImageService
from app.messaging.service import MessagingService
from app.opportunities.service import ApplicationService, OpportunityService
from app.organizations.service import OrganizationService
from app.profiles.service import ProfileService


def get_image_service() -> ImageService:
    """Dependency factory for ImageService."""
    return ImageService()


def get_opportunity_service(ctx: Annotated[RequestContext, Depends(get_context)]) -> OpportunityService:
    """Dependency factory for OpportunityService."""
    return OpportunityService(ctx.db)


def get_application_service(ctx: Annotated[RequestContext, Depends(get_context)]) -> ApplicationService:
    """Dependency factory for ApplicationService."""
    return ApplicationService(ctx.db)


def get_organization_service(ctx: Annotated[RequestContext, Depends(get_context)]) -> OrganizationService:
    """Dependency factory for OrganizationService."""
    return OrganizationService(ctx.db)


def get_profile_service(ctx: Annotated[RequestContext, Depends(get_context)]) -> ProfileService:
    """Dependency factory for ProfileService."""
    return ProfileService(ctx.db)


def get_messaging_service(ctx: Annotated[RequestContext, Depends(get_context)]) -> MessagingService:
    """Dependency factory for MessagingService."""
    return MessagingService(ctx.db)


# Type aliases for cleaner router signatures
ImageServiceDep = Annotated[ImageService, Depends(get_image_service)]
OpportunityServiceDep = Annotated[OpportunityService, Depends(get_opportunity_service)]
ApplicationServiceDep = Annotated[ApplicationService, Depends(get_application_service)]
OrganizationServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
MessagingServiceDep = Annotated[MessagingService, Depends(get_messaging_service)]


__all__ = [
    "ApplicationServiceDep",
    "ImageServiceDep",
    "MessagingServiceDep",
    "OpportunityServiceDep",
    "OrganizationServiceDep",
    "ProfileServiceDep",
    "get_application_service",
    "get_image_service",
    "get_messaging_service",
    "get_opportunity_service",
    "get_organization_service",
    "get_profile_service",
]
