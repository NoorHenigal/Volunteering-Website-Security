"""Security utilities for hashing, JWT, and authentication."""

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, Response, status
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings
from app.db.repositories import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import User


# Pydantic model for JWT payload
class TokenPayload(BaseModel):
    """JWT token payload model."""

    model_config = {"extra": "forbid"}

    sub: str
    role: str
    exp: int

    @property
    def user_id(self) -> int:
        """Get user ID as integer.

        Returns:
            User ID as integer
        """
        return int(self.sub)


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
    """Sets a cookie with standard security settings.

    Args:
        response: FastAPI Response object
        name: Cookie name
        value: Cookie value
        max_age: Optional max age in seconds
    """
    response.set_cookie(
        key=name,
        value=value,
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=max_age,
    )


def clear_cookie(response: Response, name: str) -> None:
    """Clears a cookie with standard security settings.

    Args:
        response: FastAPI Response object
        name: Cookie name
    """
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

    try:
        payload = decode_access_token(token)
        return await UserRepository.get_by_id(db, payload.user_id)
    except HTTPException:
        return None
