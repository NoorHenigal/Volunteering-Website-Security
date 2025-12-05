"""Data validation schemas for authentication."""

from typing import Literal

from pydantic import EmailStr, Field

from app.core.base_schemas import BaseCreate, BaseOut, StrictModel
from app.db.models import RoleType

__all__ = ["LoginSchema", "RegisterSchema", "TokenResponse", "UserResponse"]


class RegisterSchema(BaseCreate):
    """User registration data."""

    email: EmailStr
    password: str = Field(min_length=8)
    role: RoleType
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    username: str = Field(min_length=3, pattern=r"^[a-zA-Z0-9_-]+$")


class LoginSchema(StrictModel):
    """User login credentials."""

    email: EmailStr
    password: str


class TokenResponse(StrictModel):
    """Authentication token response."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105


class UserResponse(BaseOut):
    """User information response."""

    email: EmailStr
    role: RoleType
    first_name: str
    last_name: str
    username: str
    profile_picture: str | None
