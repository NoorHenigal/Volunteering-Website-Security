"""Authentication routes - unified API and UI."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from app.auth import service
from app.auth.schemas import LoginSchema, RegisterSchema, UserResponse
from app.core.context import RequestContext, get_context
from app.core.security import clear_auth_cookies, set_auth_cookies

router = APIRouter(prefix="/auth", tags=["Authentication"])
api_router = APIRouter(prefix="/api/auth", tags=["Authentication API"])


@router.post("/register")
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
        return ctx.error_response(str(e), status_code=422)

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
            response = ctx.success_response(redirect_url="/auth/status")
            set_auth_cookies(response, tokens.access_token)
            return response

        return ctx.success_response(data=user, status_code=201)

    except Exception as e:
        if ctx.is_ui:
            return ctx.error_response(e, template="register.html")
        raise


@router.post("/login")
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
        return ctx.error_response(str(e), status_code=422)

    try:
        tokens = await service.login_user(
            ctx.db,
            login_data.email,
            login_data.password,
            ctx.request.headers.get("user-agent"),
        )

        if ctx.is_ui:
            response = ctx.success_response(redirect_url="/auth/status")
            set_auth_cookies(response, tokens.access_token)
            return response

        return ctx.success_response(data=tokens)

    except Exception as e:
        if ctx.is_ui:
            return ctx.error_response(e, template="login.html")
        raise


@router.get("/login")
async def login_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show login page (UI only)."""
    return ctx.success_response(template="login.html")


@router.get("/register")
async def register_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show registration page (UI only)."""
    return ctx.success_response(template="register.html")


@router.post("/logout")
async def logout(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Logout user."""
    refresh_token = ctx.request.cookies.get("refresh_token")
    if refresh_token:
        await service.logout(refresh_token, ctx.db)

    response = ctx.success_response(redirect_url="/auth/login") if ctx.is_ui else ctx.success_response(data=None)
    clear_auth_cookies(response)
    return response


@router.get("/me")
async def get_current_user(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Get current user details."""
    user = ctx.require_authenticated()
    return ctx.success_response(data=UserResponse.model_validate(user))


@router.get("/status")
async def status_page(ctx: Annotated[RequestContext, Depends(get_context)]) -> Response:
    """Show status page (UI only)."""
    return ctx.success_response(template="status.html")


# API routes - expose same handlers under /api/auth prefix for JSON API clients
api_router.post("/register")(register)
api_router.post("/login")(login)
api_router.post("/logout")(logout)
api_router.get("/me")(get_current_user)
