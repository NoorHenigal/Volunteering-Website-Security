"""Authentication routes - both API and UI endpoints."""

from typing import TYPE_CHECKING, Annotated, cast

from fastapi import APIRouter, Cookie, Depends, Form, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import LoginSchema, MessageResponse, RegisterSchema, TokenResponse, UserResponse
from app.core.security import clear_auth_cookies, decode_access_token, get_user_from_cookie, set_auth_cookies
from app.db.session import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# API routes (JSON)
api_router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# UI routes (HTML forms)
ui_router = APIRouter(prefix="/auth", tags=["Auth UI"])


@api_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterSchema,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Register a new user.

    Args:
        data: Registration data
        db: Database session

    Returns:
        UserResponse with user details
    """
    return await service.register_user(data, db)


@api_router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginSchema,
    db: Annotated[AsyncSession, Depends(get_db)],
    user_agent: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    """Logs in the user and issues tokens.

    Args:
        data: Login credentials
        db: Database session
        user_agent: User agent header for device info

    Returns:
        TokenResponse with access token
    """
    return await service.login_user(db, data.email, data.password, user_agent)


@api_router.post("/refresh", response_model=TokenResponse)
async def refresh(
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    """Refresh access token using refresh token.

    Args:
        db: Database session
        refresh_token: Refresh token from cookie

    Returns:
        TokenResponse with new access token
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
        )

    return await service.refresh_tokens(refresh_token, db)


@api_router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> MessageResponse:
    """Logout user by invalidating refresh token.

    Args:
        response: FastAPI response for clearing cookies
        db: Database session
        refresh_token: Refresh token from cookie

    Returns:
        MessageResponse confirming logout
    """
    if refresh_token:
        await service.logout(refresh_token, db)

    # Clear auth cookies
    clear_auth_cookies(response)

    return MessageResponse(message="Logged out successfully")


@api_router.get("/me", response_model=UserResponse)
async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> UserResponse:
    """Returns the current authenticated user's details.

    Args:
        db: Database session
        authorization: Authorization header with Bearer token

    Returns:
        UserResponse with user details
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    token = authorization[7:]

    payload = decode_access_token(token)
    user = await service.verify_user_exists(db, payload.user_id)

    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
    )


@ui_router.get("/login")
async def login_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Shows the login form."""
    user = await get_user_from_cookie(request, db)
    return service.render(request, "login.html", user=cast("object", user))


@ui_router.post("/login")
async def login_form_post(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    user_agent: Annotated[str | None, Header()] = None,
) -> Response:
    """Logs in the user, sets the cookies, and redirects to status page."""
    try:
        tokens = await service.login_user(db, email, password, user_agent)
    except (ValueError, HTTPException) as e:
        return service.render_err(request, "login.html", e)
    else:
        response = RedirectResponse(url="/auth/status", status_code=303)
        set_auth_cookies(response, tokens.access_token)
        return response


@ui_router.get("/register")
async def register_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Shows the registration form."""
    user = await get_user_from_cookie(request, db)
    return service.render(request, "register.html", user=cast("object", user))


@ui_router.post("/register")
async def register_form_post(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    role: Annotated[str, Form(...)],
    user_agent: Annotated[str | None, Header()] = None,
) -> Response:
    """Registers a new user, logs them in, and redirects to status page."""
    try:
        tokens = await service.register_user_and_login(db, email, password, role, user_agent)
    except (ValueError, HTTPException) as e:
        return service.render_err(request, "register.html", e)
    else:
        response = RedirectResponse(url="/auth/status", status_code=303)
        set_auth_cookies(response, tokens.access_token)
        return response


@ui_router.get("/status")
async def status_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Shows the login status page."""
    user = await get_user_from_cookie(request, db)
    return service.render(request, "status.html", user=cast("object", user))


@ui_router.get("/logout")
async def logout_form() -> Response:
    """Logs out the user by clearing cookies and redirecting to login."""
    response = RedirectResponse(url="/auth/login", status_code=303)
    clear_auth_cookies(response)
    return response
