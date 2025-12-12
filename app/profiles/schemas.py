"""Profile and follow schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import field_validator

from app.core.base_schemas import BaseUpdate, StrictModel, UserFieldsMixin
from app.core.types import (
    ORM_CONFIG,
    BioField,
    LongDescriptionField,
    ProfileVisibilityField,
    ProfileVisibilityType,
)

__all__ = [
    "BaseProfileSchema",
    "FollowResponseSchema",
    "FullProfileSchema",
    "PrivacySettingsSchema",
    "ProfileUpdateSchema",
    "PublicProfileSchema",
]


class ProfileUpdateSchema(BaseUpdate):
    """Update profile bio and description."""

    bio: BioField = None
    description: LongDescriptionField = None
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    @field_validator("bio", "description", "display_name", "first_name", "last_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        """Strip whitespace and convert empty strings to None."""
        if v is None:
            return None
        v = v.strip()
        return v if v else None


class PrivacySettingsSchema(BaseUpdate):
    """Update privacy settings."""

    profile_visibility: ProfileVisibilityField | None = None
    show_email: bool | None = None
    show_organizations: bool | None = None
    searchable: bool | None = None


class BaseProfileSchema(UserFieldsMixin, StrictModel):
    """Minimal profile fields."""

    id: UUID

    model_config = ORM_CONFIG


class PublicProfileSchema(BaseProfileSchema):
    """Public profile visible to anyone."""

    bio: str | None = None
    role: str
    follower_count: int
    following_count: int


class FullProfileSchema(PublicProfileSchema):
    """Full profile with privacy-controlled fields."""

    email: str | None = None  # Only if show_email=True
    description: str | None = None
    profile_visibility: ProfileVisibilityType
    is_following: bool | None = None  # Only for authenticated non-owner viewers
    is_followed_by: bool | None = None  # Only for authenticated non-owner viewers


class FollowResponseSchema(StrictModel):
    """Follow relationship details."""

    follower_id: UUID
    followed_id: UUID
    created_at: datetime

    model_config = ORM_CONFIG
