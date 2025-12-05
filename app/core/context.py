"""Unified request context, router utilities, and template rendering."""

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


def render_template(
    request: Request,
    name: str,
    status_code: int = 200,
    **context: object,
) -> Response:
    """Render a template with context."""
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
    """Protocol for repository classes that can be used with get_or_404."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        ...

    async def get_by_id(self, obj_id: UUID) -> T | None:
        """Get entity by ID."""
        ...


TEMPLATE_REQUIRED_ERROR = "Template required for UI responses"

_DB_DEPENDENCY = Depends(get_db)
_AUTH_HEADER = Header(default=None)


def validation_error_response(e: ValidationError) -> JSONResponse:
    """Convert Pydantic ValidationError to JSON response.

    Args:
        e: Pydantic ValidationError

    Returns:
        JSONResponse with 422 status code and error details
    """
    return JSONResponse(
        status_code=422,
        content={"detail": serialize_validation_errors(e.errors()), "status_code": 422},
    )


def require_role(user: User, role: str, action: str) -> None:
    """Require user to have a specific role.

    Args:
        user: Authenticated user
        role: Required role ("organization" or "volunteer")
        action: Description of the action for error message

    Raises:
        HTTPException: 403 if user doesn't have required role
    """
    if user.role != role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {role}s can {action}",
        )


def require_organization_role(user: User) -> None:
    """Require user to have organization role.

    Args:
        user: Authenticated user

    Raises:
        HTTPException: 403 if user is not an organization user
    """
    require_role(user, "organization", "perform this action")


def require_volunteer_role(user: User) -> None:
    """Require user to have volunteer role.

    Args:
        user: Authenticated user

    Raises:
        HTTPException: 403 if user is not a volunteer
    """
    require_role(user, "volunteer", "perform this action")


class _UIRouteHandler(Protocol):
    """Protocol for UI route handlers with signature support."""

    __signature__: inspect.Signature

    def __call__(self, *args: object, **kwargs: object) -> Awaitable[Response]:
        """Call the handler."""
        ...


def ui_auth_required(func: Callable[..., Awaitable[Response]]) -> _UIRouteHandler:
    """Decorator for UI routes requiring authentication.

    Handles the common pattern of checking auth and redirecting to login.
    The decorated function receives `user` as its second argument after `ctx`.

    Usage:
        @ui_router.get("/list")
        @ui_auth_required
        async def list_items(ctx: ContextDep, user: User) -> Response:
            # user is guaranteed to be authenticated
            ...
    """
    # Get original signature and remove 'user' param (we inject it)
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


def handle_form_error(
    request: Request,
    template: str,
    error: HTTPException | Exception,
    **context: object,
) -> Response:
    """Handle form submission errors with consistent template rendering.

    Args:
        request: FastAPI request object
        template: Template name to render
        error: Exception that occurred
        **context: Additional template context

    Returns:
        Rendered template response with error message
    """
    error_msg = error.detail if isinstance(error, HTTPException) else str(error)
    return render_template(
        request,
        template,
        error=error_msg,
        status_code=400,
        **context,
    )


class RequestContext:
    """Unified request context for both API and UI."""

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

    def success_response(
        self,
        data: BaseModel | None = None,
        redirect_url: str | None = None,
        template: str | None = None,
        block: str | None = None,
        status_code: int = 200,
        **template_ctx: object,
    ) -> Response:
        """Return appropriate success response based on request type."""
        if self.is_ui:
            if redirect_url:
                if self.is_htmx:
                    return htmx_redirect(redirect_url)
                return RedirectResponse(url=redirect_url, status_code=303)

            if template and block and self.is_htmx:
                return render_block(
                    self.request,
                    template,
                    block,
                    user=self.user,
                    **template_ctx,
                )

            if not template:
                raise ValueError(TEMPLATE_REQUIRED_ERROR)
            return render_template(
                self.request,
                template,
                user=self.user,
                status_code=status_code,
                **template_ctx,
            )

        if data:
            return JSONResponse(content=data.model_dump(mode="json"), status_code=status_code)
        return JSONResponse(content={}, status_code=status_code)

    def error_response(
        self,
        error: str | Exception,
        status_code: int = 400,
        template: str | None = None,
        block: str | None = None,
        **template_ctx: object,
    ) -> Response:
        """Return appropriate error response based on request type."""
        error_msg = str(error)

        if self.is_ui:
            if template:
                if block and self.is_htmx:
                    return render_block(
                        self.request,
                        template,
                        block,
                        error=error_msg,
                        user=self.user,
                        **template_ctx,
                    )
                return render_template(
                    self.request,
                    template,
                    error=error_msg,
                    user=self.user,
                    status_code=status_code,
                    **template_ctx,
                )
            return RedirectResponse(url="/auth/login", status_code=303)

        return JSONResponse(
            content={"detail": error_msg},
            status_code=status_code,
        )

    def require_authenticated(self, redirect_to: str = "/auth/login") -> User:
        """Require user to be authenticated, redirect to login if UI."""
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
        """Require authentication for UI routes, returning redirect if not authenticated."""
        if not self.user:
            return RedirectResponse(url="/auth/login", status_code=303)
        return self.user

    async def parse_body[T: BaseModel](self, schema: type[T], form_fields: dict[str, str]) -> T | None:
        """Parse request body as JSON or form data into a Pydantic schema."""
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
                form_data = {field: str(form.get(form_name)) for field, form_name in form_fields.items()}
                return schema(**form_data)
        except ValidationError as e:
            raise RequestValidationError(e.errors()) from e

        return None

    async def parse_body_or_400[T: BaseModel](self, schema: type[T], form_fields: dict[str, str]) -> T:
        """Parse request body or raise 400 if invalid.

        Args:
            schema: Pydantic schema to validate against
            form_fields: Mapping of schema field names to form field names

        Returns:
            Validated schema instance

        Raises:
            HTTPException: 400 if body is invalid or missing
        """
        result = await self.parse_body(schema, form_fields)
        if result is None:
            raise HTTPException(status_code=400, detail="Invalid request body")
        return result

    async def get_or_404[T](
        self,
        repo_class: type[RepositoryProtocol[T]],
        entity_id: UUID,
        resource_name: str = "Resource",
    ) -> T:
        """Get entity by ID or raise HTTPException 404."""
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
    """Dependency for getting unified request context."""
    user = None
    if authorization:
        user = await get_user_from_token(authorization, db)
    else:
        user = await get_user_from_cookie(request, db)

    return RequestContext(request, db, user, authorization)


# Type alias for cleaner router code
ContextDep = Annotated[RequestContext, Depends(get_context)]


__all__ = [
    "ContextDep",
    "RequestContext",
    "get_context",
    "handle_form_error",
    "render_template",
    "require_organization_role",
    "require_role",
    "require_volunteer_role",
    "ui_auth_required",
    "validation_error_response",
]
