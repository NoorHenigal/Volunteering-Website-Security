"""Database enums for type safety."""

from enum import Enum


class RoleEnum(str, Enum):
    """User role enumeration."""

    ADMIN = "admin"
    VOLUNTEER = "volunteer"
    ORGANIZATION = "organization"
