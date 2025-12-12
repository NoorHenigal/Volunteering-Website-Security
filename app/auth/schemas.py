"""Authentication schemas."""

from typing import Literal

from pydantic import EmailStr, Field

from app.core.base_schemas import BaseCreate, BaseOut, StrictModel, UserFieldsMixin

__all__ = [
    "LoginSchema",
    "OrganizationRegisterSchema",
    "OrganizationResponse",
    "TokenResponse",
    "UserResponse",
    "VolunteerRegisterSchema",
]

UserRoleType = Literal["volunteer", "organization", "system_admin"]
AccountType = Literal["volunteer", "organization"]


class VolunteerRegisterSchema(BaseCreate):
    """Volunteer registration."""

    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    username: str = Field(min_length=3, pattern=r"^[a-zA-Z0-9_-]+$")


class OrganizationRegisterSchema(BaseCreate):
    """Organization registration."""

    name: str = Field(min_length=1, pattern=r"^[\x20-\x7E]+$")
    email: EmailStr
    password: str = Field(min_length=8)
    username: str = Field(min_length=3, pattern=r"^[a-zA-Z0-9_-]+$")  # Profile URL


class LoginSchema(StrictModel):
    """Login credentials."""

    email: EmailStr
    password: str
    account_type: AccountType = "volunteer"


class TokenResponse(StrictModel):
    """JWT token response."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    account_type: AccountType = "volunteer"


class UserResponse(UserFieldsMixin, BaseOut):
    """User details."""

    email: EmailStr
    role: UserRoleType
    bio: str | None = None
    description: str | None = None


class OrganizationResponse(BaseOut):
    """Organization details."""

    username: str
    name: str
    description: str | None = None
