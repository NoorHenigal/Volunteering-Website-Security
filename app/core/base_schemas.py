"""Base Pydantic schemas for common patterns."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.types import MUTABLE_CONFIG, NULL_BYTE_ERROR, ORM_CONFIG, STRICT_CONFIG


def request_body_from_model(
    model: type[BaseModel],
    *,
    required: bool = True,
    additional_properties: bool = False,
) -> dict[str, object]:
    """Generate openapi_extra requestBody from Pydantic model.

    Produces schema compatible with existing Schemathesis tests.

    Args:
        model: Pydantic model to generate schema from
        required: Whether the request body is required
        additional_properties: Whether to allow additional properties

    Returns:
        Dictionary suitable for FastAPI's openapi_extra parameter
    """
    schema = model.model_json_schema(mode="validation")

    # Flatten to match existing manual schemas (no $defs)
    # Extract only properties, required, type from the schema
    flat_schema: dict[str, object] = {
        "type": "object",
        "properties": schema.get("properties", {}),
        "additionalProperties": additional_properties,
    }

    # Only include required if there are required fields
    if schema.get("required"):
        flat_schema["required"] = schema["required"]

    return {
        "requestBody": {
            "required": required,
            "content": {
                "application/json": {
                    "schema": flat_schema,
                }
            },
        }
    }


OpenAPIResponseDict = dict[int | str, dict[str, object]]


class _NullByteValidator(BaseModel):
    """Mixin that rejects null bytes in all string fields."""

    @model_validator(mode="before")
    @classmethod
    def reject_null_bytes(cls, data: Any) -> Any:  # noqa: ANN401
        """Reject null bytes in all string fields globally."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and "\x00" in value:
                    msg = f"{key}: {NULL_BYTE_ERROR}"
                    raise ValueError(msg)
        return data


class StrictModel(_NullByteValidator):
    """Base model with strict validation for responses."""

    model_config = STRICT_CONFIG


class TimestampSchemaMixin(BaseModel):
    """Mixin for timestamp fields in Pydantic schemas."""

    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class UserFieldsMixin(BaseModel):
    """Mixin for common user identity fields shared across schemas.

    Used by UserResponse, BaseProfileSchema, and similar schemas
    to reduce field definition duplication.
    """

    username: str
    first_name: str
    last_name: str
    profile_picture: str | None = None


class _MutableSchemaConfig(_NullByteValidator):
    """Shared config for create/update schemas."""

    model_config = MUTABLE_CONFIG


class BaseCreate(_MutableSchemaConfig):
    """Base schema for create operations."""


class BaseUpdate(_MutableSchemaConfig):
    """Base schema for update operations."""


class BaseOut(TimestampSchemaMixin):
    """Base schema for output operations with ID and timestamps."""

    id: UUID = Field(description="Unique identifier")

    model_config = ORM_CONFIG


class HealthResponse(StrictModel):
    """Health check response."""

    status: str


class ErrorResponse(StrictModel):
    """Standardized error response."""

    detail: str
    status_code: int | None = None
    error_code: str | None = None


def error_responses(
    *,
    auth: bool = False,
    forbidden: bool = False,
    not_found: bool = False,
    bad_request: bool = True,
    conflict: bool = False,
) -> OpenAPIResponseDict:
    """Generate common error response documentation for OpenAPI.

    Args:
        auth: Include 401 Unauthorized response
        forbidden: Include 403 Forbidden response
        not_found: Include 404 Not Found response
        bad_request: Include 400 Bad Request response
        conflict: Include 409 Conflict response

    Returns:
        Dictionary of status codes to response schemas for FastAPI's `responses` parameter.
    """
    responses: OpenAPIResponseDict = {}
    if auth:
        responses[401] = {"model": ErrorResponse, "description": "Not authenticated"}
    if forbidden:
        responses[403] = {"model": ErrorResponse, "description": "Permission denied"}
    if not_found:
        responses[404] = {"model": ErrorResponse, "description": "Resource not found"}
    if bad_request:
        responses[400] = {"model": ErrorResponse, "description": "Bad request"}
    if conflict:
        responses[409] = {"model": ErrorResponse, "description": "Resource conflict"}
    return responses


class PaginationMeta(StrictModel):
    """Pagination metadata for list responses."""

    total: int | None = None
    page: int | None = None
    per_page: int | None = None


class ListResponse[T](StrictModel):
    """Generic list response wrapper."""

    items: list[T]
    meta: PaginationMeta | None = None


def list_response[T: BaseModel](items: Sequence[Any], schema: type[T]) -> ListResponse[T]:
    """Create a ListResponse from a sequence of ORM models.

    Args:
        items: Sequence of ORM models to convert
        schema: Pydantic schema to validate each item against

    Returns:
        ListResponse with validated items
    """
    return ListResponse[T](items=[schema.model_validate(i) for i in items])


__all__ = [
    "BaseCreate",
    "BaseOut",
    "BaseUpdate",
    "ErrorResponse",
    "HealthResponse",
    "ListResponse",
    "PaginationMeta",
    "StrictModel",
    "TimestampSchemaMixin",
    "UserFieldsMixin",
    "error_responses",
    "list_response",
    "request_body_from_model",
]
