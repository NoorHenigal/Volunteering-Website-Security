"""Profile schemas for user profiles and follow functionality."""

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
    """Schema for updating user bio/description."""

    bio: BioField = None
    description: LongDescriptionField = None

    @field_validator("bio", "description", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        """Strip whitespace and convert empty strings to None."""
        if v is None:
            return None
        v = v.strip()
        return v if v else None


class PrivacySettingsSchema(BaseUpdate):
    """Schema for updating privacy settings."""

    profile_visibility: ProfileVisibilityField | None = None
    show_email: bool | None = None
    show_organizations: bool | None = None
    searchable: bool | None = None


class BaseProfileSchema(UserFieldsMixin, StrictModel):
    """Base profile fields visible at all privacy levels."""

    id: UUID

    model_config = ORM_CONFIG


class PublicProfileSchema(BaseProfileSchema):
    """Public profile - visible to anyone (anonymous or authenticated)."""

    bio: str | None = None
    role: str
    follower_count: int
    following_count: int


class FullProfileSchema(PublicProfileSchema):
    """Full profile - visible to owner, followers (based on settings), or authenticated users."""

    email: str | None = None  # Only if show_email=True
    description: str | None = None
    profile_visibility: ProfileVisibilityType
    is_following: bool | None = None  # Only for authenticated non-owner viewers
    is_followed_by: bool | None = None  # Only for authenticated non-owner viewers


class FollowResponseSchema(StrictModel):
    """Response for follow operations."""

    follower_id: UUID
    followed_id: UUID
    created_at: datetime

    model_config = ORM_CONFIG
