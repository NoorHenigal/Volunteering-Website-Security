"""Authentication schemas."""

from typing import Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator

from app.core.base_schemas import BaseCreate, BaseOut, StrictModel, UserFieldsMixin
from app.core.services.encryption import decrypt_field

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

PASSWORD_MIN_LENGTH = 8
MIN_LENGTH_ERROR = "Value must be at least 8 characters"


class VolunteerRegisterSchema(BaseCreate):
    """Volunteer registration."""

    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    password: SecretStr
    username: str = Field(min_length=3, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        """Enforce minimum password length."""
        if len(value.get_secret_value()) < PASSWORD_MIN_LENGTH:
            msg = MIN_LENGTH_ERROR
            raise ValueError(msg)
        return value


class OrganizationRegisterSchema(BaseCreate):
    """Organization registration."""

    name: str = Field(min_length=1, pattern=r"^[\x20-\x7E]+$")
    email: EmailStr
    password: SecretStr
    username: str = Field(min_length=3, pattern=r"^[a-zA-Z0-9_-]+$")  # Profile URL

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        """Enforce minimum password length."""
        if len(value.get_secret_value()) < PASSWORD_MIN_LENGTH:
            msg = MIN_LENGTH_ERROR
            raise ValueError(msg)
        return value


class LoginSchema(StrictModel):
    """Login credentials."""

    email: EmailStr
    password: SecretStr
    account_type: AccountType = "volunteer"


class TokenResponse(StrictModel):
    """JWT token response."""

    access_token: str
    token_type: Literal["bearer"] = Field(default_factory=lambda: "bearer")
    account_type: AccountType = "volunteer"


class UserResponse(UserFieldsMixin, BaseOut):
    """User details."""

    email: str
    role: UserRoleType
    bio: str | None = None
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def decrypt_email(cls, data: object) -> object:
        """Decrypt email_ciphertext to email field for response."""
        if hasattr(data, "email_ciphertext"):
            data = dict(data.__dict__)
            data["email"] = decrypt_field(data.get("email_ciphertext", ""))
        elif isinstance(data, dict) and "email_ciphertext" in data:
            data["email"] = decrypt_field(data.get("email_ciphertext", ""))
        return data


class OrganizationResponse(BaseOut):
    """Organization details."""

    username: str
    name: str
    description: str | None = None
