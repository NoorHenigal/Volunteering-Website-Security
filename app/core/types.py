"""Shared type definitions and reusable Pydantic validators.

This module provides common type aliases and annotated validators
for consistent validation across the application.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Path
from pydantic import AfterValidator, ConfigDict, Field

# Error messages
NULL_BYTE_ERROR = "Null bytes are not allowed in this field"


def no_null_bytes(value: str | None) -> str | None:
    """Reject strings containing null bytes.

    Args:
        value: String value to validate

    Returns:
        The original value if valid

    Raises:
        ValueError: If the string contains null bytes
    """
    if value is not None and "\x00" in value:
        raise ValueError(NULL_BYTE_ERROR)
    return value


# Reusable validator for null bytes
NullByteValidator = AfterValidator(no_null_bytes)


# ConfigDict Constants
STRICT_CONFIG = ConfigDict(strict=True, extra="forbid")
ORM_CONFIG = ConfigDict(from_attributes=True)
MUTABLE_CONFIG = ConfigDict(
    from_attributes=True,
    str_strip_whitespace=True,
    validate_assignment=True,
)


# Annotated Field Types

# Standard name field with length constraints
NameField = Annotated[
    str,
    Field(min_length=1, max_length=255, description="Name field. Whitespace is trimmed; cannot be whitespace-only."),
    NullByteValidator,
]

# Description field with length constraint
DescriptionField = Annotated[
    str | None,
    Field(default=None, max_length=1000),
    NullByteValidator,
]

# Title field for opportunities
TitleField = Annotated[
    str,
    Field(min_length=1, max_length=255, description="Title field. Whitespace is trimmed; cannot be whitespace-only."),
    NullByteValidator,
]

# Location field
LocationField = Annotated[
    str | None,
    Field(default=None, max_length=255),
    NullByteValidator,
]

# Profile-related types
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
ProfileVisibilityField = Annotated[ProfileVisibilityType, Field()]

# Reusable path parameter types with regex validation
UsernamePath = Annotated[str, Path(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")]
SlugPath = Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")]

# UUID path parameter types for improved OpenAPI documentation
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
    "OpportunityIdPath",
    "OrganizationIdPath",
    "ProfileVisibilityField",
    "ProfileVisibilityType",
    "SlugPath",
    "TitleField",
    "UsernamePath",
    "no_null_bytes",
]
