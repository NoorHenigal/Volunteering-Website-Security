"""Authentication routes - unified API and UI."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from app.auth import service
from app.auth.schemas import LoginSchema, RegisterSchema, TokenResponse, UserResponse
from app.core.base_schemas import ErrorResponse, request_body_from_model
from app.core.context import RequestContext, get_context, validation_error_response
from app.core.htmx import htmx_redirect
from app.core.security import clear_auth_cookies, set_auth_cookies

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse | None,
    responses={201: {"model": UserResponse}, 400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    openapi_extra=request_body_from_model(RegisterSchema),
)
async def register(
    ctx: Annotated[RequestContext, Depends(get_context)],
) -> Response:
    """Register new user - handles both API and UI requests."""
    try:
        reg_data = await ctx.parse_body(
            RegisterSchema,
            {
                "email": "email",
                "password": "password",
                "role": "role",
                "first_name": "first_name",
                "last_name": "last_name",
                "username": "username",
            },
        )
        if not reg_data:
            return ctx.error_response("Invalid content type", status_code=400)
    except ValidationError as e:
        return validation_error_response(e)

    try:
        user = await service.register_user(reg_data, ctx.db)

        # For UI, also log them in
        if ctx.is_ui:
            tokens = await service.login_user(
                ctx.db,
                reg_data.email,
                reg_data.password,
                ctx.request.headers.get("user-agent"),
            )

            if ctx.is_htmx:
                response = htmx_redirect("/auth/status")
            else:
                response = ctx.success_response(redirect_url="/auth/status")

            set_auth_cookies(response, tokens.access_token)
            return response

        return ctx.success_response(data=user, status_code=201)

    except Exception as e:
        if ctx.is_ui:
            return ctx.error_response(e, template="register.html", block="register_form")
        raise


@router.post(
    "/login",
    response_model=TokenResponse | None,
    responses={200: {"model": TokenResponse}, 400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    openapi_extra=request_body_from_model(LoginSchema),
)
async def login(
    ctx: Annotated[RequestContext, Depends(get_context)],
) -> Response:
    """Login - handles both API and UI requests."""
    try:
        login_data = await ctx.parse_body(
            LoginSchema,
            {"email": "email", "password": "password"},
        )
        if not login_data:
            return ctx.error_response("Invalid content type", status_code=400)
    except ValidationError as e:
        return validation_error_response(e)

    try:
        tokens = await service.login_user(
            ctx.db,
            login_data.email,
            login_data.password,
            ctx.request.headers.get("user-agent"),
        )

        if ctx.is_ui:
            if ctx.is_htmx:
                response = htmx_redirect("/auth/status")
            else:
                response = ctx.success_response(redirect_url="/auth/status")

            set_auth_cookies(response, tokens.access_token)
            return response

        return ctx.success_response(data=tokens)

    except Exception as e:
        if ctx.is_ui:
            return ctx.error_response(e, template="login.html", block="login_form")
        raise


@router.get("/login", include_in_schema=False)
async def login_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show login page (UI only)."""
    return ctx.success_response(template="login.html")


@router.get("/register", include_in_schema=False)
async def register_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show registration page (UI only)."""
    return ctx.success_response(template="register.html")


@router.post(
    "/logout",
    response_model=None,
    responses={200: {"description": "Logout successful"}, 400: {"model": ErrorResponse}},
)
async def logout(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Logout user."""
    refresh_token = ctx.request.cookies.get("refresh_token")
    if refresh_token:
        await service.logout(refresh_token, ctx.db)

    if ctx.is_ui:
        response = htmx_redirect("/auth/login") if ctx.is_htmx else ctx.success_response(redirect_url="/auth/login")
    else:
        response = ctx.success_response(data=None)

    clear_auth_cookies(response)
    return response


@router.get(
    "/me",
    response_model=UserResponse,
    responses={200: {"model": UserResponse}, 401: {"model": ErrorResponse}},
)
async def get_current_user(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Get current user details."""
    user = ctx.require_authenticated()
    return ctx.success_response(data=UserResponse.model_validate(user))


@router.get("/status", include_in_schema=False)
async def status_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show status page (UI only)."""
    return ctx.success_response(template="status.html")
