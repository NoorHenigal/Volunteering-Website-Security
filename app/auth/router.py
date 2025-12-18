"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.auth import service
from app.auth.schemas import (
    LoginSchema,
    OrganizationRegisterSchema,
    VolunteerRegisterSchema,
)
from app.core.context import RequestContext, get_context
from app.core.htmx import htmx_redirect
from app.core.security import clear_auth_cookies, set_auth_cookies
from app.core.types import UI_RESPONSES

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
    else:
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
    return await ctx.success_response(data=UserResponse.model_validate(user))


@router.get("/event-statistics", include_in_schema=False)
async def event_statistics_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show event statistics page (UI only)."""
    return await render_template(ctx.request, "pages/event_statistics.html", user=ctx.user)


@router.get("/admin-statistics", include_in_schema=False)
async def admin_statistics_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show admin statistics page (UI only)."""
    return await render_template(ctx.request, "pages/admin_statistics.html", user=ctx.user)
