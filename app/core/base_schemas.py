"""Base Pydantic schemas for common patterns."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.types import MUTABLE_CONFIG, ORM_CONFIG, STRICT_CONFIG


class StrictModel(BaseModel):
    """Base model with strict validation for responses."""

    model_config = STRICT_CONFIG


class TimestampMixin(BaseModel):
    """Mixin for timestamp fields in Pydantic schemas."""

    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class _MutableSchemaConfig(BaseModel):
    """Shared config for create/update schemas."""

    model_config = MUTABLE_CONFIG


class BaseCreate(_MutableSchemaConfig):
    """Base schema for create operations."""


class BaseUpdate(_MutableSchemaConfig):
    """Base schema for update operations."""


class BaseOut(TimestampMixin):
    """Base schema for output operations with ID and timestamps."""

    id: UUID = Field(description="Unique identifier")

    model_config = ORM_CONFIG


class ListResponse[T](StrictModel):
    """Generic list response wrapper."""

    items: list[T]


__all__ = [
    "BaseCreate",
    "BaseOut",
    "BaseUpdate",
    "ListResponse",
    "StrictModel",
]
