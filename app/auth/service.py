"""Authentication service: registration, login, and token management."""

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.profiles import RFC_9106_HIGH_MEMORY, RFC_9106_LOW_MEMORY
from fastapi import HTTPException, status
from jose import jwt

from app.auth.schemas import (
    AccountType,
    OrganizationRegisterSchema,
    OrganizationResponse,
    TokenResponse,
    UserResponse,
    VolunteerRegisterSchema,
)
from app.core.config import settings
from app.core.exceptions import require
from app.db.models import Organization, RefreshToken, User, UserOrganizationRole
from app.db.repositories import OrganizationRepository, RefreshTokenRepository, UserRepository

_params = RFC_9106_HIGH_MEMORY if settings.argon2_profile == "RFC_9106_HIGH_MEMORY" else RFC_9106_LOW_MEMORY

_ph = PasswordHasher.from_parameters(_params)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def hash_password(password: str) -> str:
    """Hash password with Argon2id."""
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Check if password matches hash."""
    try:
        _ph.verify(hashed, password)
    except VerifyMismatchError:
        return False
    else:
        return True


def create_jwt_token(entity_id: UUID, role_or_type: str, account_type: AccountType = "volunteer") -> str:
    """Create a JWT access token."""
    expire = datetime.now(UTC) + settings.access_token_expiry
    to_encode = {
        "sub": str(entity_id),
        "role": role_or_type,
        "account_type": account_type,
        "exp": int(expire.timestamp()),
    }
    encoded: str = jwt.encode(
        to_encode,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return encoded


def generate_refresh_token() -> str:
    """Generate a secure random refresh token."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage."""
    return hash_password(token)


async def _get_token_by_cookie(
    refresh_cookie: str,
    db: AsyncSession,
) -> tuple[RefreshTokenRepository, RefreshToken | None]:
    """Get refresh token from cookie hash."""
    token_hash = hash_refresh_token(refresh_cookie)
    token_repo = RefreshTokenRepository(db)
    db_token = await token_repo.get_by_token_hash(token_hash)
    return token_repo, db_token


async def verify_user_exists(db: AsyncSession, user_id: UUID) -> User:
    """Get user by ID or raise 401."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    return require(user, "User not found", status.HTTP_401_UNAUTHORIZED)


async def validate_refresh_token(refresh_cookie: str, db: AsyncSession) -> tuple[User, object]:
    """Validate refresh token, return user and token or raise 401."""
    require(refresh_cookie, "Refresh token not found", status.HTTP_401_UNAUTHORIZED)

    token_repo, db_token = await _get_token_by_cookie(refresh_cookie, db)
    validated_token = require(db_token, "Invalid refresh token", status.HTTP_401_UNAUTHORIZED)

    if validated_token.expires_at < datetime.now(UTC):
        await token_repo.delete(validated_token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = await verify_user_exists(db, validated_token.user_id)
    return user, validated_token


async def register_volunteer(data: VolunteerRegisterSchema, db: AsyncSession) -> UserResponse:
    """Register a new volunteer account."""
    user_repo = UserRepository(db)
    org_repo = OrganizationRepository(db)

    # Check if email already exists (in users or orgs)
    if await user_repo.find_one(User.email == data.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Check if username already exists (in users or orgs)
    if await user_repo.find_one(User.username == data.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    if await org_repo.find_one(Organization.username == data.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    # Create new user (role defaults to volunteer)
    new_user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        username=data.username,
    )
    new_user = await user_repo.create(new_user)
    return UserResponse.model_validate(new_user)


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User:
    """Authenticate user by email/password or raise 401."""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(email)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return user


async def issue_user_tokens(user: User, device: str | None, db: AsyncSession) -> TokenResponse:
    """Create access and refresh tokens for a user."""
    access_token = create_jwt_token(user.id, user.role, "volunteer")

    # Generate and store refresh token
    refresh_token = generate_refresh_token()
    token_hash = hash_refresh_token(refresh_token)
    expires_at = datetime.now(UTC) + settings.refresh_token_expiry

    token_repo = RefreshTokenRepository(db)
    refresh_token_obj = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        device_info=device,
    )
    await token_repo.create(refresh_token_obj)

    return TokenResponse(access_token=access_token, account_type="volunteer")


async def register_organization(data: OrganizationRegisterSchema, db: AsyncSession) -> OrganizationResponse:
    """Register a new organization account."""
    user_repo = UserRepository(db)
    org_repo = OrganizationRepository(db)

    if await user_repo.find_one(User.email == data.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    if await user_repo.find_one(User.username == data.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    if await org_repo.find_one(Organization.username == data.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    backend_user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        username=data.username,
        role="organization",
        first_name=data.name,
        last_name=None,
    )
    backend_user = await user_repo.create(backend_user)

    new_org = Organization(
        username=data.username,
        name=data.name,
    )
    new_org = await org_repo.create(new_org)

    user_org_role = UserOrganizationRole(
        user_id=backend_user.id,
        organization_id=new_org.id,
        role="admin",
    )
    db.add(user_org_role)
    await db.flush()  # Flush to get IDs without committing - let get_db() handle commit
    await db.refresh(new_org)
    return OrganizationResponse.model_validate(new_org)


async def authenticate_organization(email: str, password: str, db: AsyncSession) -> User:
    """Authenticate organization by email/password or raise 401."""
    user = await authenticate_user(email, password, db)
    if user.role != "organization":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not an organization account",
        )
    return user


async def issue_org_tokens(user: User) -> TokenResponse:
    """Create access token for an organization."""
    access_token = create_jwt_token(user.id, "organization", "organization")
    return TokenResponse(access_token=access_token, account_type="organization")


async def login_entity(
    db: AsyncSession,
    email: str,
    password: str,
    account_type: AccountType,
    user_agent: str | None,
) -> TokenResponse:
    """Log in user or organization and return tokens."""
    if account_type == "organization":
        user = await authenticate_organization(email, password, db)
        return await issue_org_tokens(user)
    user = await authenticate_user(email, password, db)
    return await issue_user_tokens(user, user_agent, db)


async def refresh_tokens(refresh_cookie: str, db: AsyncSession) -> TokenResponse:
    """Create new access token from refresh token."""
    user, _db_token = await validate_refresh_token(refresh_cookie, db)
    access_token = create_jwt_token(user.id, user.role, "volunteer")
    return TokenResponse(access_token=access_token, account_type="volunteer")


async def logout(refresh_cookie: str, db: AsyncSession) -> None:
    """Delete refresh token to log out."""
    require(refresh_cookie, "Refresh token not found", status.HTTP_401_UNAUTHORIZED)
    token_repo, db_token = await _get_token_by_cookie(refresh_cookie, db)
    if db_token:
        await token_repo.delete(db_token)


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    user_agent: str | None,
) -> TokenResponse:
    """Legacy alias for login_entity with volunteer account type."""
    return await login_entity(db, email, password, "volunteer", user_agent)
