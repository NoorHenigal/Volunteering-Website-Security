"""Base Pydantic schemas and response helpers."""

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
    """Generate OpenAPI requestBody schema from a Pydantic model."""
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
    """Rejects null bytes in all string fields."""

    @model_validator(mode="before")
    @classmethod
    def reject_null_bytes(cls, data: Any) -> Any:  # noqa: ANN401
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and "\x00" in value:
                    msg = f"{key}: {NULL_BYTE_ERROR}"
                    raise ValueError(msg)
        return data


class StrictModel(_NullByteValidator):
    """Strict model that forbids extra fields."""

    model_config = STRICT_CONFIG


class TimestampSchemaMixin(BaseModel):
    """Adds created_at and updated_at fields."""

    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class UserFieldsMixin(BaseModel):
    """Common user identity fields (username, names, profile picture)."""

    username: str
    first_name: str | None = None
    last_name: str | None = None
    profile_picture: str | None = None


class _MutableSchemaConfig(_NullByteValidator):
    """Base for create/update schemas with whitespace stripping."""

    model_config = MUTABLE_CONFIG


class BaseCreate(_MutableSchemaConfig):
    """Base for resource creation schemas."""


class BaseUpdate(_MutableSchemaConfig):
    """Base for resource update schemas."""


class BaseOut(TimestampSchemaMixin):
    """Base response schema with ID and timestamps."""

    id: UUID

    model_config = ORM_CONFIG


class ErrorResponse(StrictModel):
    """API error response."""

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
    """Build OpenAPI error response documentation."""
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
    """Pagination metadata."""

    total: int | None = None
    page: int | None = None
    per_page: int | None = None


class ListResponse[T](StrictModel):
    """Paginated list response."""

    items: list[T]
    meta: PaginationMeta | None = None


def list_response[T: BaseModel](items: Sequence[Any], schema: type[T]) -> ListResponse[T]:
    """Convert ORM models to a ListResponse."""
    return ListResponse[T](items=[schema.model_validate(i) for i in items])


__all__ = [
    "BaseCreate",
    "BaseOut",
    "BaseUpdate",
    "ErrorResponse",
    "ListResponse",
    "PaginationMeta",
    "StrictModel",
    "TimestampSchemaMixin",
    "UserFieldsMixin",
    "error_responses",
    "list_response",
    "request_body_from_model",
]
