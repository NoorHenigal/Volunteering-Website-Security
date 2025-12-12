"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.auth import service
from app.auth.schemas import (
    LoginSchema,
    OrganizationRegisterSchema,
    OrganizationResponse,
    TokenResponse,
    UserResponse,
    VolunteerRegisterSchema,
)
from app.core.base_schemas import ErrorResponse, request_body_from_model
from app.core.context import RequestContext, get_context, validation_error_response
from app.core.htmx import htmx_redirect
from app.core.security import clear_auth_cookies, set_auth_cookies

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register/volunteer",
    response_model=UserResponse | None,
    responses={201: {"model": UserResponse}, 400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    openapi_extra=request_body_from_model(VolunteerRegisterSchema),
)
async def register_volunteer(
    ctx: Annotated[RequestContext, Depends(get_context)],
) -> Response:
    """Register new volunteer account."""
    try:
        reg_data = await ctx.parse_body(
            VolunteerRegisterSchema,
            {
                "email": "email",
                "password": "password",
                "first_name": "first_name",
                "last_name": "last_name",
                "username": "username",
            },
        )
        if not reg_data:
            return await ctx.error_response("Invalid content type", status_code=400)
    except (ValidationError, RequestValidationError) as e:
        if ctx.is_ui:
            return await ctx.error_response(e, template="pages/auth.html", block="content", active_tab="volunteer")
        return validation_error_response(e)

    try:
        user = await service.register_volunteer(reg_data, ctx.db)

        # For UI, also log them in
        if ctx.is_ui:
            tokens = await service.login_entity(
                ctx.db,
                reg_data.email,
                reg_data.password,
                "volunteer",
                ctx.request.headers.get("user-agent"),
            )

            if ctx.is_htmx:
                response = await htmx_redirect("/")
            else:
                response = await ctx.success_response(redirect_url="/")

            set_auth_cookies(response, tokens.access_token)
            return response

        return await ctx.success_response(data=user, status_code=201)

    except Exception as e:
        if ctx.is_ui:
            return await ctx.error_response(e, template="pages/auth.html", block="content", active_tab="volunteer")
        raise


@router.post(
    "/register/organization",
    response_model=OrganizationResponse | None,
    responses={201: {"model": OrganizationResponse}, 400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    openapi_extra=request_body_from_model(OrganizationRegisterSchema),
)
async def register_organization(
    ctx: Annotated[RequestContext, Depends(get_context)],
) -> Response:
    """Register new organization account."""
    try:
        reg_data = await ctx.parse_body(
            OrganizationRegisterSchema,
            {
                "email": "email",
                "password": "password",
                "username": "username",
                "name": "name",
            },
        )
        if not reg_data:
            return await ctx.error_response("Invalid content type", status_code=400)
    except (ValidationError, RequestValidationError) as e:
        if ctx.is_ui:
            return await ctx.error_response(e, template="pages/auth.html", block="content", active_tab="organization")
        return validation_error_response(e)

    try:
        org = await service.register_organization(reg_data, ctx.db)

        # For UI, also log them in
        if ctx.is_ui:
            tokens = await service.login_entity(
                ctx.db,
                reg_data.email,
                reg_data.password,
                "organization",
                ctx.request.headers.get("user-agent"),
            )

            if ctx.is_htmx:
                response = await htmx_redirect("/")
            else:
                response = await ctx.success_response(redirect_url="/")

            set_auth_cookies(response, tokens.access_token)
            return response

        return await ctx.success_response(data=org, status_code=201)

    except Exception as e:
        if ctx.is_ui:
            return await ctx.error_response(e, template="pages/auth.html", block="content", active_tab="organization")
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
    """Login - handles both volunteer and organization accounts."""
    try:
        login_data = await ctx.parse_body(
            LoginSchema,
            {"email": "email", "password": "password", "account_type": "account_type"},
        )
        if not login_data:
            return await ctx.error_response("Invalid content type", status_code=400)
    except (ValidationError, RequestValidationError) as e:
        if ctx.is_ui:
            return await ctx.error_response(e, template="pages/auth.html", block="content")
        return validation_error_response(e)

    try:
        tokens = await service.login_entity(
            ctx.db,
            login_data.email,
            login_data.password,
            login_data.account_type,
            ctx.request.headers.get("user-agent"),
        )

        if ctx.is_ui:
            if ctx.is_htmx:
                response = await htmx_redirect("/")
            else:
                response = await ctx.success_response(redirect_url="/")

            set_auth_cookies(response, tokens.access_token)
            return response

        return await ctx.success_response(data=tokens)

    except Exception as e:
        if ctx.is_ui:
            return await ctx.error_response(e, template="pages/auth.html", block="content")
        raise


@router.get("/login", include_in_schema=False)
async def login_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show login page (UI only)."""
    form_config = {
        "title": "Welcome Back",
        "subtitle": "Sign in to your account",
        "container_id": "login-container",
        "action": "/auth/login",
        "fields": [
            {
                "name": "email",
                "type": "email",
                "label": "Email",
                "placeholder": "you@example.com",
                "required": True,
                "show_label": True,
            },
            {
                "name": "password",
                "type": "password",
                "label": "Password",
                "placeholder": "",
                "required": True,
                "show_label": True,
            },
            {
                "name": "account_type",
                "type": "select",
                "label": "Account Type",
                "placeholder": "Select account type",
                "required": True,
                "show_label": True,
                "options": [("volunteer", "Volunteer"), ("organization", "Organization")],
                "default": "volunteer",
            },
        ],
        "submit_text": "Sign In",
        "footer_text": "Don't have an account?",
        "footer_link": "/auth/register",
        "footer_link_text": "Create one",
    }
    return await ctx.success_response(template="pages/auth.html", form_config=form_config, view="login")


@router.get("/register", include_in_schema=False)
async def register_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show registration page with tabbed interface (UI only)."""
    # Configuration for volunteer registration form
    volunteer_form = {
        "action": "/auth/register/volunteer",
    }

    # Configuration for organization registration form
    organization_form = {
        "action": "/auth/register/organization",
    }

    return await ctx.success_response(
        template="pages/auth.html",
        view="register",
        volunteer_form=volunteer_form,
        organization_form=organization_form,
        active_tab="volunteer",
    )


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
        response = (
            await htmx_redirect("/auth/login")
            if ctx.is_htmx
            else await ctx.success_response(redirect_url="/auth/login")
        )
    else:
        response = await ctx.success_response(data=None)

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
    return await ctx.success_response(data=UserResponse.model_validate(user))
