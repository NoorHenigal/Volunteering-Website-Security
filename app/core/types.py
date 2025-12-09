"""Shared type definitions and validators."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Path
from pydantic import AfterValidator, ConfigDict, Field

NULL_BYTE_ERROR = "Null bytes are not allowed in this field"


def no_null_bytes(value: str | None) -> str | None:
    """Reject strings containing null bytes."""
    if value is not None and "\x00" in value:
        raise ValueError(NULL_BYTE_ERROR)
    return value


NullByteValidator = AfterValidator(no_null_bytes)


STRICT_CONFIG = ConfigDict(strict=True, extra="forbid")
ORM_CONFIG = ConfigDict(from_attributes=True)
MUTABLE_CONFIG = ConfigDict(
    from_attributes=True,
    str_strip_whitespace=True,
    validate_assignment=True,
)


NameField = Annotated[
    str,
    Field(min_length=1, max_length=255, description="Name field. Whitespace is trimmed; cannot be whitespace-only."),
    NullByteValidator,
]

DescriptionField = Annotated[
    str | None,
    Field(default=None, max_length=1000),
    NullByteValidator,
]

TitleField = Annotated[
    str,
    Field(min_length=1, max_length=255, description="Title field. Whitespace is trimmed; cannot be whitespace-only."),
    NullByteValidator,
]

LocationField = Annotated[
    str | None,
    Field(default=None, max_length=255),
    NullByteValidator,
]

ProfileVisibilityType = Literal["public", "authenticated", "followers", "private"]
BioField = Annotated[
    str | None,
    Field(max_length=200),
    NullByteValidator,
]
LongDescriptionField = Annotated[
    str | None,
    Field(max_length=1000),
    NullByteValidator,
]

OpportunityDescriptionField = Annotated[
    str,
    Field(min_length=1, max_length=5000, description="Opportunity description"),
    NullByteValidator,
]

ProfileVisibilityField = Annotated[ProfileVisibilityType, Field()]

OrganizationRoleType = Literal["admin", "member"]
OrganizationRoleField = Annotated[OrganizationRoleType, Field(description="Organization role: admin or member")]

UsernamePath = Annotated[str, Path(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")]
SlugPath = Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")]

OpportunityIdPath = Annotated[UUID, Path(description="Opportunity UUID")]
OrganizationIdPath = Annotated[UUID, Path(description="Organization UUID")]
ApplicationIdPath = Annotated[UUID, Path(description="Application UUID")]


__all__ = [
    "MUTABLE_CONFIG",
    "NULL_BYTE_ERROR",
    "ORM_CONFIG",
    "STRICT_CONFIG",
    "ApplicationIdPath",
    "BioField",
    "DescriptionField",
    "LocationField",
    "LongDescriptionField",
    "NameField",
    "NullByteValidator",
    "OpportunityDescriptionField",
    "OpportunityIdPath",
    "OrganizationIdPath",
    "ProfileVisibilityField",
    "ProfileVisibilityType",
    "SlugPath",
    "TitleField",
    "UsernamePath",
    "no_null_bytes",
]
