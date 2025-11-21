"""Data validation schemas for authentication."""

from typing import Literal

from pydantic import BaseModel, EmailStr


class StrictModel(BaseModel):
    """Base model with strict validation."""

    model_config = {"strict": True, "extra": "forbid"}


class RegisterSchema(StrictModel):
    """User registration data."""

    email: EmailStr
    password: str
    role: Literal["admin", "volunteer", "organization"]


class LoginSchema(StrictModel):
    """User login credentials."""

    email: EmailStr
    password: str


class TokenResponse(StrictModel):
    """Authentication token response."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105


class UserResponse(StrictModel):
    """User information response."""

    id: int
    email: EmailStr
    role: str


class MessageResponse(StrictModel):
    """Simple message response."""

    message: str
