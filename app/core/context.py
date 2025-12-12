"""Request context and response helpers."""

import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Annotated, Protocol, cast, runtime_checkable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import serialize_validation_errors
from app.core.htmx import htmx_redirect, is_htmx, render_block
from app.core.security import get_user_from_cookie, get_user_from_token
from app.db.session import get_db

if TYPE_CHECKING:
    from app.db.models import User


from app.core.templates import templates


async def render_template(
    request: Request,
    name: str,
    status_code: int = 200,
    block: str | None = None,
    **context: object,
) -> Response:
    """Render a Jinja2 template. If block is specified, renders only that block."""
    # If block is specified, use render_block for partial rendering
    if block:
        return await render_block(request, name, block, **context)

    # Otherwise, render the full template
    ctx = dict(context)
    ctx.setdefault("request", request)
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


def validation_error_response(e: ValidationError | RequestValidationError) -> JSONResponse:
    """Convert validation error to 422 JSON response."""
    return JSONResponse(
        status_code=422,
        content={"detail": serialize_validation_errors(e.errors()), "status_code": 422},
    )


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
    """Decorator that redirects to login if not authenticated. Injects `user` as second arg."""
    original_sig = inspect.signature(func)
    params = [p for p in original_sig.parameters.values() if p.name not in ("user", "_user")]
    new_sig = original_sig.replace(parameters=params)

    @wraps(func)
    async def wrapper(ctx: RequestContext, *args: object, **kwargs: object) -> Response:
        result = ctx.require_ui_auth()
        if isinstance(result, RedirectResponse):
            return result
        # Inject user as second positional argument
        return await func(ctx, result, *args, **kwargs)

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
        self.is_ui = self.is_htmx or (not authorization and "text/html" in request.headers.get("accept", ""))

    async def success_response(
        self,
        data: BaseModel | None = None,
        redirect_url: str | None = None,
        template: str | None = None,
        block: str | None = None,
        status_code: int = 200,
        **template_ctx: object,
    ) -> Response:
        """Return JSON for API requests, template/redirect for UI."""
        if self.is_ui:
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

        if data:
            return JSONResponse(content=data.model_dump(mode="json"), status_code=status_code)
        return JSONResponse(content={}, status_code=status_code)

    async def error_response(
        self,
        error: str | Exception,
        status_code: int = 400,
        template: str | None = None,
        block: str | None = None,
        **template_ctx: object,
    ) -> Response:
        """Return JSON error for API, template with error for UI."""
        error_msg = str(error)

        if self.is_ui:
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
            return RedirectResponse(url="/auth/login", status_code=303)

        return JSONResponse(
            content={"detail": error_msg, "status_code": status_code, "error_code": None},
            status_code=status_code,
        )

    def require_authenticated(self, redirect_to: str = "/auth/login") -> User:
        """Return user or raise 401 (API) / redirect (UI)."""
        if not self.user:
            if self.is_ui:
                raise HTTPException(
                    status_code=status.HTTP_303_SEE_OTHER,
                    detail=redirect_to,
                    headers={"Location": redirect_to},
                )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return self.user

    def require_ui_auth(self) -> User | RedirectResponse:
        """Return user or redirect response for UI routes."""
        if not self.user:
            return RedirectResponse(url="/auth/login", status_code=303)
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
                form = await self.request.form()
                form_data = {}
                for field, form_name in form_fields.items():
                    value = form.get(form_name)
                    if value is not None:
                        form_data[field] = str(value)
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
    "validation_error_response",
]
