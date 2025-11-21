"""User repository for centralized user database access."""

from typing import TYPE_CHECKING

from sqlalchemy import select

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RefreshToken, User


class UserRepository:
    """Repository for User model database operations."""

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
        """Get user by ID.

        Args:
            db: Database session
            user_id: User ID to lookup

        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        """Get user by email.

        Args:
            db: Database session
            email: Email address to lookup

        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, email: str, password_hash: str, role: str) -> User:
        """Creates a new user.

        Args:
            db: Database session
            email: User email
            password_hash: Hashed password
            role: User role

        Returns:
            Created User object
        """
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


class RefreshTokenRepository:
    """Repository for RefreshToken model database operations."""

    @staticmethod
    async def get_by_token_hash(db: AsyncSession, token_hash: str) -> RefreshToken | None:
        """Get refresh token by token hash.

        Args:
            db: Database session
            token_hash: Hashed token to lookup

        Returns:
            RefreshToken object if found, None otherwise
        """
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        device_info: str | None = None,
    ) -> RefreshToken:
        """Creates a new refresh token.

        Args:
            db: Database session
            user_id: User ID
            token_hash: Hashed token
            expires_at: Expiration datetime
            device_info: Optional device information

        Returns:
            Created RefreshToken object
        """
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            device_info=device_info,
        )
        db.add(refresh_token)
        await db.commit()
        await db.refresh(refresh_token)
        return refresh_token

    @staticmethod
    async def delete(db: AsyncSession, refresh_token: RefreshToken) -> None:
        """Delete a refresh token.

        Args:
            db: Database session
            refresh_token: RefreshToken object to delete
        """
        await db.delete(refresh_token)
        await db.commit()
