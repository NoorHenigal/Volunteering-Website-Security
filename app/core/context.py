"""Request context and response helpers."""

import inspect
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Annotated, Protocol, cast, runtime_checkable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, SecretBytes, SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.htmx import htmx_redirect, is_htmx, render_block, render_error_page
from app.core.security import get_user_from_cookie, get_user_from_token
from app.core.templates import templates
from app.db.session import get_db

log = logging.getLogger(__name__)

REDACTED = "**********"
SECRET_TYPES = (SecretStr, SecretBytes)


def _get_secret_field_names(schema: type[BaseModel]) -> set[str]:
    """Extract field names that are typed as SecretStr or SecretBytes."""
    secret_fields: set[str] = set()
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        origin = getattr(annotation, "__origin__", None)
        if origin is not None:
            args = getattr(annotation, "__args__", ())
            if any(isinstance(arg, type) and issubclass(arg, SECRET_TYPES) for arg in args if isinstance(arg, type)):
                secret_fields.add(field_name)
        elif isinstance(annotation, type) and issubclass(annotation, SECRET_TYPES):
            secret_fields.add(field_name)
    return secret_fields


def _redact_dict(data: dict[str, object], secret_keys: set[str]) -> dict[str, object]:
    """Return a copy of data with secret keys redacted."""
    return {k: REDACTED if k in secret_keys else v for k, v in data.items()}


if TYPE_CHECKING:
    from app.db.models import User


async def render_template(
    request: Request,
    name: str,
    status_code: int = 200,
    block: str | None = None,
    **context: object,
) -> Response:
    """Render a Jinja2 template. If block is specified, renders only that block."""
    if block:
        return await render_block(request, name, block, **context)

    ctx = dict(context)
    ctx.setdefault("request", request)
    ctx.setdefault("csrf_token", getattr(request.state, "csrf_token", None) or request.cookies.get("csrf_token"))
    return templates.TemplateResponse(
        request,
        name,
        ctx,
        status_code=status_code,
    )


@runtime_checkable
class RepositoryProtocol[T](Protocol):
    """Repository with get_by_id method."""

    def __init__(self, session: AsyncSession) -> None: ...
    async def get_by_id(self, obj_id: UUID) -> T | None: ...


TEMPLATE_REQUIRED_ERROR = "Template required for UI responses"

_DB_DEPENDENCY = Depends(get_db)
_AUTH_HEADER = Header(default=None)


def require_role(user: User, role: str, action: str) -> None:
    """Raise 403 if user doesn't have the required role."""
    if user.role != role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {role}s can {action}",
        )


def require_system_admin(user: User) -> None:
    """Raise 403 if user is not a system admin."""
    require_role(user, "system_admin", "perform this action")


def require_volunteer_role(user: User) -> None:
    """Raise 403 if user is not a volunteer."""
    require_role(user, "volunteer", "perform this action")


class _UIRouteHandler(Protocol):
    """UI route handler protocol."""

    __signature__: inspect.Signature

    def __call__(self, *args: object, **kwargs: object) -> Awaitable[Response]: ...


def ui_auth_required(func: Callable[..., Awaitable[Response]]) -> _UIRouteHandler:
    """Decorator that requires authentication. Raises 401 if not authenticated. Injects `user` as second arg."""
    original_sig = inspect.signature(func)
    params = [p for p in original_sig.parameters.values() if p.name not in ("user", "_user")]
    new_sig = original_sig.replace(parameters=params)

    @wraps(func)
    async def wrapper(ctx: RequestContext, *args: object, **kwargs: object) -> Response:
        user = ctx.require_authenticated()
        # Inject user as second positional argument
        return await func(ctx, user, *args, **kwargs)

    object.__setattr__(wrapper, "__signature__", new_sig)
    return cast("_UIRouteHandler", wrapper)


async def handle_form_error(
    request: Request,
    template: str,
    error: HTTPException | Exception,
    **context: object,
) -> Response:
    """Render template with error message for form submission failures."""
    error_msg = error.detail if isinstance(error, HTTPException) else str(error)
    return await render_template(
        request,
        template,
        status_code=400,
        block=None,
        error=error_msg,
        **context,
    )


class RequestContext:
    """Unified request context for API and UI routes."""

    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        user: User | None = None,
        authorization: str | None = None,
    ) -> None:
        """Initialize request context."""
        self.request = request
        self.db = db
        self.user = user
        self.authorization = authorization
        self.is_htmx = is_htmx(request)

    async def success_response(
        self,
        redirect_url: str | None = None,
        template: str | None = None,
        block: str | None = None,
        status_code: int = 200,
        **template_ctx: object,
    ) -> Response:
        """Return template or redirect for UI requests."""
        if redirect_url:
            if self.is_htmx:
                return await htmx_redirect(redirect_url)
            return RedirectResponse(url=redirect_url, status_code=303)

        if template and block and self.is_htmx:
            return await render_block(
                self.request,
                template,
                block,
                user=self.user,
                **template_ctx,
            )

        if not template:
            raise ValueError(TEMPLATE_REQUIRED_ERROR)
        return await render_template(
            self.request,
            template,
            status_code=status_code,
            block=None,
            user=self.user,
            **template_ctx,
        )

    async def error_response(
        self,
        error: str | Exception,
        status_code: int = 400,
        template: str | None = None,
        block: str | None = None,
        **template_ctx: object,
    ) -> Response:
        """Return template with error for UI requests."""
        if isinstance(error, HTTPException):
            error_msg = str(error.detail)
            status_code = error.status_code
        else:
            error_msg = str(error)

        if template:
            if block and self.is_htmx:
                return await render_block(
                    self.request,
                    template,
                    block,
                    error=error_msg,
                    user=self.user,
                    **template_ctx,
                )
            return await render_template(
                self.request,
                template,
                status_code=status_code,
                block=None,
                error=error_msg,
                user=self.user,
                **template_ctx,
            )
        if self.is_htmx:
            error_html = f'<div class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm font-medium">{error_msg}</div>'
            return Response(content=error_html, media_type="text/html", status_code=status_code)
        # Return HTML error page for non-HTMX requests using template
        return await render_error_page(self.request, status_code, f"Error {status_code}", error_msg)

    def require_authenticated(self) -> User:
        """Return user or raise 401 if not authenticated."""
        if not self.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return self.user

    async def parse_body[T: BaseModel](self, schema: type[T], form_fields: dict[str, str]) -> T | None:
        """Parse JSON or form data into schema, or None if invalid content type."""
        content_type = self.request.headers.get("content-type", "")

        try:
            if "application/json" in content_type:
                body = await self.request.json()
                # Ensure body is a dict, not an array or primitive
                if not isinstance(body, dict):
                    title = "parse_body"
                    raise ValidationError.from_exception_data(
                        title,
                        [
                            {
                                "type": "dict_type",
                                "loc": ("body",),
                                "input": body,
                            }
                        ],
                    )
                return schema(**body)

            if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                form = getattr(self.request.state, "_cached_form", None)
                if form is None:
                    form = await self.request.form()

                # Detect secret fields from schema for redaction
                secret_fields = _get_secret_field_names(schema)
                # Map form field names to schema field names for redaction
                form_name_to_schema = {v: k for k, v in form_fields.items()}
                secret_form_keys = {fn for fn, sf in form_name_to_schema.items() if sf in secret_fields}
                secret_form_keys.add("csrf_token")

                if log.isEnabledFor(logging.DEBUG):
                    log.debug("[MULTIPART] Parsing form for schema: %s", schema.__name__)
                    log.debug("[MULTIPART] Expected fields: %s", form_fields)
                    log.debug("[MULTIPART] Received form data keys: %s", list(form.keys()))
                    for key, value in form.items():
                        if key in secret_form_keys:
                            log.debug("[MULTIPART] Field '%s': %s", key, REDACTED)
                        else:
                            value_preview = str(value)[:100] if value else "[EMPTY]"
                            log.debug("[MULTIPART] Field '%s': %s", key, value_preview)

                form_data: dict[str, object] = {}
                for field, form_name in form_fields.items():
                    value = form.get(form_name)
                    if value is not None:
                        str_value = str(value).strip()
                        if str_value == "":
                            field_info = schema.model_fields.get(field)
                            if field_info and field_info.is_required() is False:
                                log.debug("[MULTIPART] Skipping optional empty field: %s", form_name)
                                continue
                        field_info = schema.model_fields.get(field)
                        if field_info and field_info.annotation is UUID:
                            form_data[field] = UUID(str_value)
                        else:
                            form_data[field] = str_value

                if log.isEnabledFor(logging.DEBUG):
                    log.debug(
                        "[MULTIPART] Final form_data for schema validation: %s", _redact_dict(form_data, secret_fields)
                    )

                return schema(**form_data)
        except ValidationError as e:
            raise RequestValidationError(e.errors()) from e

        return None

    async def parse_body_or_400[T: BaseModel](self, schema: type[T], form_fields: dict[str, str]) -> T:
        """Parse request body or raise 400."""
        try:
            result = await self.parse_body(schema, form_fields)
            if result is None:
                raise HTTPException(status_code=400, detail="Invalid request body")
        except RequestValidationError as e:
            # Flatten errors to a string for simple display
            error_msgs = []
            for err in e.errors():
                loc = err.get("loc", [])
                field = loc[-1] if loc else "Unknown"
                msg = err.get("msg", "Invalid value")
                error_msgs.append(f"{field}: {msg}")

            raise HTTPException(status_code=400, detail=" | ".join(error_msgs)) from e
        else:
            return result

    async def get_or_404[T](
        self,
        repo_class: type[RepositoryProtocol[T]],
        entity_id: UUID,
        resource_name: str = "Resource",
    ) -> T:
        """Get entity by ID or raise 404."""
        repo = repo_class(self.db)
        entity = await repo.get_by_id(entity_id)
        if entity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource_name} not found")
        return entity


async def get_context(
    request: Request,
    db: AsyncSession = _DB_DEPENDENCY,
    authorization: str | None = _AUTH_HEADER,
) -> RequestContext:
    """FastAPI dependency that builds RequestContext."""
    user = None
    if authorization:
        user = await get_user_from_token(authorization, db)
    else:
        user = await get_user_from_cookie(request, db)

    return RequestContext(request, db, user, authorization)


ContextDep = Annotated[RequestContext, Depends(get_context)]


__all__ = [
    "ContextDep",
    "RequestContext",
    "get_context",
    "handle_form_error",
    "render_template",
    "require_role",
    "require_system_admin",
    "require_volunteer_role",
    "ui_auth_required",
]
