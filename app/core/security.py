"""Security utilities for hashing, JWT, and authentication."""

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, Request, Response, status
from jose import JWTError, jwt

from app.core.base_schemas import StrictModel
from app.core.config import settings
from app.db.models import RoleType
from app.db.repositories import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import User


class TokenPayload(StrictModel):
    """JWT token payload model with strict validation."""

    sub: str
    role: RoleType
    exp: int

    @property
    def user_id(self) -> UUID:
        """Get user ID as UUID.

        Returns:
            User ID as UUID
        """
        return UUID(self.sub)


def decode_access_token(token: str) -> TokenPayload:
    """Decodes and validates a JWT access token.

    Args:
        token: JWT token string to decode

    Returns:
        Validated TokenPayload model

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        # Validate required fields exist
        if "sub" not in payload or "role" not in payload or "exp" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return TokenPayload(**payload)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e!s}",
        ) from e


def set_cookie(response: Response, name: str, value: str, max_age: int | None = None) -> None:
    """Sets a cookie with standard security settings."""
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )


def clear_cookie(response: Response, name: str) -> None:
    """Clears a cookie with standard security settings."""
    response.delete_cookie(
        key=name,
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )


def set_auth_cookies(response: Response, access_token: str, refresh_token: str | None = None) -> None:
    """Set authentication cookies in response.

    Args:
        response: FastAPI Response object
        access_token: Access token to set
        refresh_token: Optional refresh token to set
    """
    set_cookie(response, "access_token", access_token)
    if refresh_token:
        set_cookie(response, "refresh_token", refresh_token)


def clear_auth_cookies(response: Response) -> None:
    """Clear both access and refresh token cookies.

    Args:
        response: FastAPI Response object
    """
    clear_cookie(response, "access_token")
    clear_cookie(response, "refresh_token")


async def _get_user_from_token(token: str, db: AsyncSession) -> User | None:
    """Get user from a JWT token string.

    Args:
        token: JWT token string
        db: Database session

    Returns:
        User object if valid token, None otherwise
    """
    try:
        payload = decode_access_token(token)
        user_repo = UserRepository(db)
        return await user_repo.get_by_id(payload.user_id)
    except HTTPException:
        return None


async def get_user_from_cookie(request: Request, db: AsyncSession) -> User | None:
    """Gets the current user from the access_token cookie.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    return await _get_user_from_token(token, db)


async def get_user_from_token(authorization: str | None, db: AsyncSession) -> User | None:
    """Gets the current user from the Authorization header.

    Args:
        authorization: Authorization header with Bearer token
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return await _get_user_from_token(authorization[7:], db)


__all__ = [
    "clear_auth_cookies",
    "get_user_from_cookie",
    "get_user_from_token",
    "set_auth_cookies",
]
