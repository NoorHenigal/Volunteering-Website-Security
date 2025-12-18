"""Admin schemas for dashboard statistics."""

from pydantic import EmailStr, Field, SecretStr, field_validator

from app.auth.schemas import _validate_password
from app.core.base_schemas import BaseCreate, StrictModel


class PlatformStats(StrictModel):
    """Platform-wide statistics for admin dashboard."""

    total_users: int
    total_organizations: int
    total_opportunities: int
    total_applications: int
    pending_applications: int
    active_users: int
    active_organizations: int


class ActivityDataPoint(StrictModel):
    """Single data point for activity chart."""

    label: str
    users: int
    opportunities: int
    applications: int


class AdminSetupSchema(BaseCreate):
    """Schema for initial admin account setup (first login)."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: SecretStr
    confirm_password: SecretStr

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        """Validate password meets requirements."""
        return _validate_password(value)

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password(cls, value: SecretStr) -> SecretStr:
        """Validate confirm password meets requirements."""
        return _validate_password(value)


__all__ = [
    "ActivityDataPoint",
    "AdminSetupSchema",
    "PlatformStats",
]
