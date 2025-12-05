"""Handles user login, registration, and token stuff. Keeps things simple."""

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status
from jose import jwt

from app.auth.schemas import RegisterSchema, TokenResponse, UserResponse
from app.core.config import settings
from app.db.models import RefreshToken, User
from app.db.repositories import RefreshTokenRepository, UserRepository

_ph = PasswordHasher(
    time_cost=4,
    memory_cost=512,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def hash_password(password: str) -> str:
    """Hashes a password securely using Argon2id.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string
    """
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Checks if a password matches its hash.

    Args:
        password: Plain text password to verify
        hashed: Hashed password to check against

    Returns:
        True if password matches, False otherwise
    """
    try:
        _ph.verify(hashed, password)
    except VerifyMismatchError:
        return False
    else:
        return True


def create_jwt_token(user_id: UUID, role: str) -> str:
    """Creates a JWT access token for a user.

    Args:
        user_id: User ID to encode in token
        role: User role to encode in token

    Returns:
        Encoded JWT token string
    """
    expire = datetime.now(UTC) + settings.access_token_expiry
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": int(expire.timestamp()),
    }
    encoded: str = jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return encoded


def generate_refresh_token() -> str:
    """Generates a secure random refresh token.

    Returns:
        Random token string (64 characters)
    """
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage.

    Args:
        token: Plain refresh token to hash

    Returns:
        Hashed token string
    """
    return hash_password(token)


async def _get_token_by_cookie(
    refresh_cookie: str,
    db: AsyncSession,
) -> tuple[RefreshTokenRepository, RefreshToken | None]:
    """Get refresh token from cookie hash.

    Args:
        refresh_cookie: Refresh token from cookie
        db: Database session

    Returns:
        Tuple of (repository, token or None)
    """
    token_hash = hash_refresh_token(refresh_cookie)
    token_repo = RefreshTokenRepository(db)
    db_token = await token_repo.get_by_token_hash(token_hash)
    return token_repo, db_token


def require[T](entity: T | None, message: str, code: int = 401) -> T:
    """Require entity to exist, otherwise raise error.

    Args:
        entity: Entity to check
        message: Error message
        code: HTTP status code

    Returns:
        Entity if it exists

    Raises:
        HTTPException: If entity is None
    """
    if not entity:
        raise HTTPException(status_code=code, detail=message)
    return entity


async def verify_user_exists(db: AsyncSession, user_id: UUID) -> User:
    """Verifies a user exists by ID.

    Args:
        db: Database session
        user_id: User ID to verify

    Returns:
        User model

    Raises:
        HTTPException: If user not found
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    return require(user, "User not found")


async def validate_refresh_token(refresh_cookie: str, db: AsyncSession) -> tuple[User, object]:
    """Validates refresh token and returns user and token.

    Args:
        refresh_cookie: Refresh token from cookie
        db: Database session

    Returns:
        Tuple of (User, RefreshToken)

    Raises:
        HTTPException: If token is invalid or expired
    """
    require(refresh_cookie, "Refresh token not found")

    token_repo, db_token = await _get_token_by_cookie(refresh_cookie, db)
    validated_token = require(db_token, "Invalid refresh token")

    if validated_token.expires_at < datetime.now(UTC):
        await token_repo.delete(validated_token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = await verify_user_exists(db, validated_token.user_id)
    return user, validated_token


async def register_user(data: RegisterSchema, db: AsyncSession) -> UserResponse:
    """Registers a new user account.

    Args:
        data: Registration data with email, password, and role
        db: Database session

    Returns:
        UserResponse with user details

    Raises:
        HTTPException: If email already exists
    """
    # Check if user already exists
    user_repo = UserRepository(db)
    existing_user = await user_repo.get_by_email(data.email)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    hashed_password = hash_password(data.password)
    new_user = User(
        email=data.email,
        password_hash=hashed_password,
        role=data.role,
        first_name=data.first_name,
        last_name=data.last_name,
        username=data.username,
    )
    new_user = await user_repo.create(new_user)

    return UserResponse.model_validate(new_user)


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User:
    """Checks if email and password match a user.

    Args:
        email: User email
        password: Plain text password
        db: Database session

    Returns:
        Authenticated User model

    Raises:
        HTTPException: If credentials are invalid
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(email)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return user


async def issue_tokens(user: User, device: str | None, db: AsyncSession) -> TokenResponse:
    """Creates access and refresh tokens for a user.

    Args:
        user: User model to issue tokens for
        device: Optional device information
        db: Database session

    Returns:
        TokenResponse with access token
    """
    # Create access token
    access_token = create_jwt_token(user.id, user.role)

    # Generate and store refresh token
    refresh_token = generate_refresh_token()
    token_hash = hash_refresh_token(refresh_token)

    # Calculate expiry
    expires_at = datetime.now(UTC) + settings.refresh_token_expiry

    # Store refresh token in database
    token_repo = RefreshTokenRepository(db)
    refresh_token_obj = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        device_info=device,
    )
    await token_repo.create(refresh_token_obj)

    return TokenResponse(access_token=access_token)


async def refresh_tokens(refresh_cookie: str, db: AsyncSession) -> TokenResponse:
    """Creates a new access token using a refresh token.

    Args:
        refresh_cookie: Refresh token from cookie
        db: Database session

    Returns:
        TokenResponse with new access token

    Raises:
        HTTPException: If refresh token is invalid or expired
    """
    # Validate refresh token and get user
    user, _db_token = await validate_refresh_token(refresh_cookie, db)

    # Create new access token
    access_token = create_jwt_token(user.id, user.role)

    return TokenResponse(access_token=access_token)


async def logout(refresh_cookie: str, db: AsyncSession) -> None:
    """Logs out a user by deleting their refresh token.

    Args:
        refresh_cookie: Refresh token from cookie
        db: Database session

    Raises:
        HTTPException: If refresh token is invalid
    """
    require(refresh_cookie, "Refresh token not found")

    token_repo, db_token = await _get_token_by_cookie(refresh_cookie, db)
    if db_token:
        await token_repo.delete(db_token)


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    user_agent: str | None,
) -> TokenResponse:
    """Logs in a user and returns tokens.

    Args:
        db: Database session
        email: User email
        password: User password
        user_agent: Optional device info

    Returns:
        TokenResponse with access token

    Raises:
        HTTPException: If credentials are invalid
    """
    user = await authenticate_user(email, password, db)
    return await issue_tokens(user, user_agent, db)
