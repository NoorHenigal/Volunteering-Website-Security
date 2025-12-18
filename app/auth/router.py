"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy import select

from app.admin.schemas import AdminSetupSchema
from app.auth import service
from app.auth.schemas import (
    LoginSchema,
    OrganizationRegisterSchema,
    VolunteerRegisterSchema,
)
from app.core.context import RequestContext, get_context, render_template, require_system_admin
from app.core.htmx import htmx_redirect
from app.core.security import clear_auth_cookies, set_auth_cookies
from app.core.services.encryption import encrypt_field, hash_email
from app.core.types import UI_RESPONSES
from app.db.models import User

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    default_response_class=HTMLResponse,
    responses=UI_RESPONSES,
)


def _login_form_config() -> dict[str, object]:
    return {
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


def _register_forms() -> tuple[dict[str, object], dict[str, object]]:
    return ({"action": "/auth/register/volunteer"}, {"action": "/auth/register/organization"})


@router.post("/register/volunteer")
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
            volunteer_form, organization_form = _register_forms()
            return await ctx.error_response(
                "Invalid content type",
                template="pages/auth.html",
                block="content",
                view="register",
                hide_chrome=True,
                volunteer_form=volunteer_form,
                organization_form=organization_form,
                active_tab="volunteer",
            )
    except (ValidationError, RequestValidationError) as e:
        volunteer_form, organization_form = _register_forms()
        return await ctx.error_response(
            e,
            template="pages/auth.html",
            block="content",
            view="register",
            hide_chrome=True,
            volunteer_form=volunteer_form,
            organization_form=organization_form,
            active_tab="volunteer",
        )

    try:
        await service.register_volunteer(reg_data, ctx.db)

        tokens = await service.login_entity(
            ctx.db,
            reg_data.email,
            reg_data.password,
            "volunteer",
            ctx.request.headers.get("user-agent"),
        )
    except (ValueError, HTTPException) as e:
        volunteer_form, organization_form = _register_forms()
        return await ctx.error_response(
            e,
            template="pages/auth.html",
            block="content",
            view="register",
            hide_chrome=True,
            volunteer_form=volunteer_form,
            organization_form=organization_form,
            active_tab="volunteer",
        )
    else:
        if ctx.is_htmx:
            response = await htmx_redirect("/")
        else:
            response = await ctx.success_response(redirect_url="/")

        set_auth_cookies(response, tokens.access_token)
        return response


@router.post("/register/organization")
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
            volunteer_form, organization_form = _register_forms()
            return await ctx.error_response(
                "Invalid content type",
                template="pages/auth.html",
                block="content",
                view="register",
                hide_chrome=True,
                volunteer_form=volunteer_form,
                organization_form=organization_form,
                active_tab="organization",
            )
    except (ValidationError, RequestValidationError) as e:
        volunteer_form, organization_form = _register_forms()
        return await ctx.error_response(
            e,
            template="pages/auth.html",
            block="content",
            view="register",
            hide_chrome=True,
            volunteer_form=volunteer_form,
            organization_form=organization_form,
            active_tab="organization",
        )

    try:
        await service.register_organization(reg_data, ctx.db)

        tokens = await service.login_entity(
            ctx.db,
            reg_data.email,
            reg_data.password,
            "organization",
            ctx.request.headers.get("user-agent"),
        )
    except (ValueError, HTTPException) as e:
        volunteer_form, organization_form = _register_forms()
        return await ctx.error_response(
            e,
            template="pages/auth.html",
            block="content",
            view="register",
            hide_chrome=True,
            volunteer_form=volunteer_form,
            organization_form=organization_form,
            active_tab="organization",
        )
    else:
        if ctx.is_htmx:
            response = await htmx_redirect("/")
        else:
            response = await ctx.success_response(redirect_url="/")

        set_auth_cookies(response, tokens.access_token)
        return response


@router.post("/login")
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
            return await ctx.error_response(
                "Invalid content type",
                template="pages/auth.html",
                block="content",
                view="login",
                hide_chrome=True,
                form_config=_login_form_config(),
            )
    except (ValidationError, RequestValidationError) as e:
        return await ctx.error_response(
            e,
            template="pages/auth.html",
            block="content",
            view="login",
            hide_chrome=True,
            form_config=_login_form_config(),
        )

    try:
        tokens = await service.login_entity(
            ctx.db,
            login_data.email,
            login_data.password,
            login_data.account_type,
            ctx.request.headers.get("user-agent"),
        )
    except (ValueError, HTTPException) as e:
        return await ctx.error_response(
            e,
            template="pages/auth.html",
            block="content",
            view="login",
            hide_chrome=True,
            form_config=_login_form_config(),
        )

    # Check if this is an admin who needs to complete setup
    user = await service.authenticate_user(login_data.email, login_data.password, ctx.db)
    if user.role == "system_admin" and user.requires_password_reset:
        # Set auth cookies so they're authenticated, then show setup form
        response = await ctx.success_response(
            template="pages/auth.html",
            view="admin_setup",
            hide_chrome=True,
        )
        set_auth_cookies(response, tokens.access_token)
        return response

    if ctx.is_htmx:
        response = await htmx_redirect("/")
    else:
        response = await ctx.success_response(redirect_url="/")

    set_auth_cookies(response, tokens.access_token)
    return response


@router.get("/login", include_in_schema=False)
async def login_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show login page."""
    return await ctx.success_response(
        template="pages/auth.html",
        form_config=_login_form_config(),
        view="login",
        hide_chrome=True,
    )


@router.get("/register", include_in_schema=False)
async def register_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show registration page with tabbed interface."""
    volunteer_form, organization_form = _register_forms()

    return await ctx.success_response(
        template="pages/auth.html",
        view="register",
        hide_chrome=True,
        volunteer_form=volunteer_form,
        organization_form=organization_form,
        active_tab="volunteer",
    )


@router.post("/admin-setup", include_in_schema=False)
async def admin_setup_submit(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Process admin setup form submission from login page."""
    user = ctx.require_authenticated()
    require_system_admin(user)

    if not user.requires_password_reset:
        if ctx.is_htmx:
            return await htmx_redirect("/admin/dashboard")
        return await ctx.success_response(redirect_url="/admin/dashboard")

    try:
        data = await ctx.parse_body(
            AdminSetupSchema,
            {
                "first_name": "first_name",
                "last_name": "last_name",
                "username": "username",
                "email": "email",
                "password": "password",
                "confirm_password": "confirm_password",
            },
        )
        if not data:
            return await ctx.error_response(
                "Invalid form data",
                template="pages/auth.html",
                view="admin_setup",
                hide_chrome=True,
            )
    except (ValidationError, RequestValidationError) as e:
        return await ctx.error_response(
            e,
            template="pages/auth.html",
            view="admin_setup",
            hide_chrome=True,
        )

    if data.password.get_secret_value() != data.confirm_password.get_secret_value():
        return await ctx.error_response(
            "Passwords do not match",
            template="pages/auth.html",
            view="admin_setup",
            hide_chrome=True,
        )

    # Check email uniqueness
    existing_email = await ctx.db.execute(
        select(User).where(User.email_hash == hash_email(data.email), User.id != user.id)
    )
    if existing_email.scalar_one_or_none():
        return await ctx.error_response(
            "Email already in use",
            template="pages/auth.html",
            view="admin_setup",
            hide_chrome=True,
        )

    # Check username uniqueness
    existing_username = await ctx.db.execute(select(User).where(User.username == data.username, User.id != user.id))
    if existing_username.scalar_one_or_none():
        return await ctx.error_response(
            "Username already taken",
            template="pages/auth.html",
            view="admin_setup",
            hide_chrome=True,
        )

    # Update user credentials
    user.first_name = data.first_name
    user.last_name = data.last_name
    user.username = data.username
    user.email_ciphertext = encrypt_field(data.email) or ""
    user.email_hash = hash_email(data.email)
    user.password_hash = service.hash_password(data.password.get_secret_value())
    user.requires_password_reset = False

    await ctx.db.commit()

    # Issue new token without the requires_password_reset flag
    new_token = service.create_jwt_token(user.id, user.role, "volunteer", requires_password_reset=False)

    if ctx.is_htmx:
        response = await htmx_redirect("/admin/dashboard")
    else:
        response = await ctx.success_response(redirect_url="/admin/dashboard")

    set_auth_cookies(response, new_token)
    return response


@router.post("/logout")
async def logout(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Logout user."""
    refresh_token = ctx.request.cookies.get("refresh_token")
    if refresh_token:
        await service.logout(refresh_token, ctx.db)

    response = (
        await htmx_redirect("/auth/login") if ctx.is_htmx else await ctx.success_response(redirect_url="/auth/login")
    )

    clear_auth_cookies(response)
    return response


@router.get("/me")
async def get_current_user(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Get current user details - redirects to profile page."""
    user = ctx.require_authenticated()
    return await ctx.success_response(redirect_url=f"/{user.username}")


@router.get("/event-statistics", include_in_schema=False)
async def event_statistics_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show event statistics page (UI only)."""
    return await render_template(ctx.request, "pages/event_statistics.html", user=ctx.user)


@router.get("/admin-statistics", include_in_schema=False)
async def admin_statistics_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show admin statistics page (UI only, system_admin only)."""
    user = ctx.require_authenticated()
    require_system_admin(user)
    return await render_template(ctx.request, "pages/admin_statistics.html", user=user)
