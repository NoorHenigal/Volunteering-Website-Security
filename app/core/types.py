"""Shared type definitions and reusable Pydantic validators.

This module provides common type aliases and annotated validators
for consistent validation across the application.
"""

from typing import Annotated

from pydantic import ConfigDict, Field

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
NameField = Annotated[str, Field(min_length=1, max_length=255)]

# Description field with length constraint
DescriptionField = Annotated[str | None, Field(default=None, max_length=1000)]

# Title field for opportunities
TitleField = Annotated[str, Field(min_length=1, max_length=255)]

# Location field
LocationField = Annotated[str | None, Field(default=None, max_length=255)]


__all__ = [
    "MUTABLE_CONFIG",
    "ORM_CONFIG",
    "STRICT_CONFIG",
    "DescriptionField",
    "LocationField",
    "NameField",
    "TitleField",
]
