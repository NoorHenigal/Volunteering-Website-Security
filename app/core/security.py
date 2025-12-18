"""Security utilities: JWT decoding and cookie management."""

from typing import TYPE_CHECKING, Literal
from uuid import UUID

from fastapi import HTTPException, Request, Response, status
from jose import JWTError, jwt

from app.core.base_schemas import StrictModel
from app.core.config import settings
from app.db.repositories import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import User

AccountType = Literal["volunteer", "organization"]


class TokenPayload(StrictModel):
    """Decoded JWT payload."""

    sub: str
    role: str  # Can be user role or "organization"
    exp: int
    account_type: AccountType = "volunteer"
    rpr: bool = False  # requires_password_reset flag

    @property
    def entity_id(self) -> UUID:
        """User or organization ID."""
        return UUID(self.sub)

    @property
    def user_id(self) -> UUID:
        """Alias for entity_id."""
        return self.entity_id


def decode_access_token(token: str) -> TokenPayload:
    """Decode JWT access token or raise 401."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
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
    """Set a cookie with configured security settings."""
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
    """Delete a cookie."""
    response.delete_cookie(
        key=name,
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )


def set_auth_cookies(response: Response, access_token: str, refresh_token: str | None = None) -> None:
    """Set access and optional refresh token cookies."""
    set_cookie(response, "access_token", access_token)
    if refresh_token:
        set_cookie(response, "refresh_token", refresh_token)


def clear_auth_cookies(response: Response) -> None:
    """Clear authentication cookies."""
    clear_cookie(response, "access_token")
    clear_cookie(response, "refresh_token")


async def _get_user_from_token(token: str, db: AsyncSession) -> User | None:
    """Get user from JWT token, or None if invalid."""
    try:
        payload = decode_access_token(token)
        user_repo = UserRepository(db)
        return await user_repo.get_by_id(payload.user_id)
    except HTTPException:
        return None


async def get_user_from_cookie(request: Request, db: AsyncSession) -> User | None:
    """Get user from access_token cookie, or None if not authenticated."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    return await _get_user_from_token(token, db)


async def get_user_from_token(authorization: str | None, db: AsyncSession) -> User | None:
    """Get user from Authorization header, or None if not authenticated."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return await _get_user_from_token(authorization[7:], db)


__all__ = [
    "clear_auth_cookies",
    "get_user_from_cookie",
    "get_user_from_token",
    "set_auth_cookies",
]
