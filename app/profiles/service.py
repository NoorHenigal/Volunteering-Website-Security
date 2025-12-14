"""Profile and follow business logic."""

import logging
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import require
from app.core.service import BaseService
from app.db.models import Application, Follow, RefreshToken, User
from app.db.repositories import FollowRepository, UserRepository
from app.profiles.schemas import (
    FullProfileSchema,
    PrivacySettingsSchema,
    ProfileUpdateSchema,
    PublicProfileSchema,
)

log = logging.getLogger(__name__)

__all__ = ["ProfileService"]


class ProfileService(BaseService):
    """Service for profile management and follow functionality."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session."""
        super().__init__(db)
        self.user_repo = UserRepository(db)
        self.follow_repo = FollowRepository(db)

    async def get_profile(
        self,
        username: str,
        viewer: User | None,
    ) -> PublicProfileSchema | FullProfileSchema:
        """Get user profile with visibility based on privacy settings."""
        profile_user = require(await self.user_repo.get_by_username(username), "User not found")

        # Check if viewer can see full profile
        can_view_full = await self._can_view_full_profile(profile_user, viewer)

        if not can_view_full:
            # Check privacy settings and raise appropriate errors
            if profile_user.profile_visibility == "private":
                # Hide existence of private profiles
                raise HTTPException(status_code=404, detail="User not found")

            if profile_user.profile_visibility == "authenticated":
                raise HTTPException(status_code=403, detail="Authentication required to view this profile")

            if profile_user.profile_visibility == "followers":
                raise HTTPException(status_code=403, detail="Must follow user to view profile")

            # Fallback for any other case (shouldn't be reached)
            return await self._to_public_profile(profile_user)

        # Build full profile, calculate counts only when needed
        follower_count = await self.follow_repo.get_follower_count(profile_user.id)
        following_count = await self.follow_repo.get_following_count(profile_user.id)

        is_following: bool | None = None
        is_followed_by: bool | None = None

        if viewer and viewer.id != profile_user.id:
            is_following = await self.follow_repo.is_following(viewer.id, profile_user.id)
            is_followed_by = await self.follow_repo.is_following(profile_user.id, viewer.id)

        return FullProfileSchema(
            id=profile_user.id,
            username=profile_user.username,
            first_name=profile_user.first_name,
            last_name=profile_user.last_name,
            profile_picture=profile_user.profile_picture,
            bio=profile_user.bio,
            role=profile_user.role,
            follower_count=follower_count,
            following_count=following_count,
            email=profile_user.email if profile_user.show_email else None,
            description=profile_user.description,
            profile_visibility=profile_user.profile_visibility,  # type: ignore[arg-type]
            is_following=is_following,
            is_followed_by=is_followed_by,
        )

    async def _can_view_full_profile(self, profile_user: User, viewer: User | None) -> bool:
        """Check if viewer can see full profile."""
        visibility = profile_user.profile_visibility

        # Owner can always see their own full profile
        if viewer and viewer.id == profile_user.id:
            return True

        if visibility == "public":
            return True

        if visibility == "authenticated":
            return viewer is not None

        if visibility == "followers":
            if viewer is None:
                return False
            return await self.follow_repo.is_following(viewer.id, profile_user.id)

        # private - only owner can see (handled above)
        return False

    async def update_profile(self, user: User, data: ProfileUpdateSchema) -> User:
        """Update user profile fields."""
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(user, field, value)

        return await self.user_repo.update(user)

    async def deactivate_user(self, user: User) -> None:
        """Soft-delete a user account by deactivating, anonymizing, and revoking refresh tokens."""
        if user.is_active:
            user.is_active = False
            await self.user_repo.update(user)

        await self.anonymize_user(user)

        await self.db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
        await self.db.flush()

    async def anonymize_user(self, user: User) -> None:
        """Anonymize user PII for erasure while preserving row and FK integrity."""
        if user.email.startswith("deleted-user-") and user.username.startswith("deleted-user-"):
            return

        suffix = uuid4().hex
        email = f"deleted-user-{suffix}@example.invalid"
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError:
            email = f"deleted-user-{suffix}@example.com"
        user.email = email
        user.username = f"deleted-user-{suffix}"
        user.first_name = None
        user.last_name = None
        user.ip_address = None
        user.bio = None
        user.description = None
        user.profile_picture = None
        user.custom_display_name = None
        user.profile_visibility = "private"
        user.searchable = False
        user.show_email = False

        await self.user_repo.update(user)

        await self.db.execute(update(Application).where(Application.volunteer_id == user.id).values(message=None))
        await self.db.flush()

    async def update_privacy_settings(self, user: User, data: PrivacySettingsSchema) -> User:
        """Update user privacy settings."""
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            # Skip null values - don't overwrite existing settings with null
            if value is not None:
                setattr(user, field, value)

        return await self.user_repo.update(user)

    async def follow_user(self, follower: User, followed_username: str) -> Follow:
        """Create follow relationship."""
        followed = require(await self.user_repo.get_by_username(followed_username), "User not found")

        if follower.id == followed.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot follow yourself")

        # Check if already following
        existing = await self.follow_repo.get_follow(follower.id, followed.id)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following this user")

        return await self.follow_repo.create_follow(follower.id, followed.id)

    async def unfollow_user(self, follower: User, followed_username: str) -> None:
        """Remove follow relationship."""
        followed = require(await self.user_repo.get_by_username(followed_username), "User not found")

        await self.follow_repo.delete_follow(follower.id, followed.id)

    async def get_followers(
        self,
        username: str,
        viewer: User | None,
    ) -> list[PublicProfileSchema]:
        """Get list of followers for a user."""
        user = require(await self.user_repo.get_by_username(username), "User not found")

        if not await self._can_view_followers(user, viewer):
            return []

        follows = await self.follow_repo.get_followers(user.id)
        users = [f.follower for f in follows]
        return await self._to_public_profiles_batch(users)

    async def get_following(
        self,
        username: str,
        viewer: User | None,
    ) -> list[PublicProfileSchema]:
        """Get list of users that a user follows."""
        user = require(await self.user_repo.get_by_username(username), "User not found")

        if not await self._can_view_followers(user, viewer):
            return []

        follows = await self.follow_repo.get_following(user.id)
        users = [f.followed for f in follows]
        return await self._to_public_profiles_batch(users)

    async def _can_view_followers(self, user: User, viewer: User | None) -> bool:
        """Check if viewer can see followers/following lists."""
        # Owner can always see their own lists
        if viewer and viewer.id == user.id:
            return True

        # For now, follow the same rules as profile visibility
        return await self._can_view_full_profile(user, viewer)

    async def _to_public_profile(self, user: User) -> PublicProfileSchema:
        """Convert User to PublicProfileSchema."""
        follower_count = await self.follow_repo.get_follower_count(user.id)
        following_count = await self.follow_repo.get_following_count(user.id)

        return PublicProfileSchema(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            profile_picture=user.profile_picture,
            bio=user.bio,
            role=user.role,
            follower_count=follower_count,
            following_count=following_count,
        )

    async def _to_public_profiles_batch(self, users: list[User]) -> list[PublicProfileSchema]:
        """Convert multiple Users to PublicProfileSchema with batch count fetching.

        This eliminates N+1 queries by fetching all counts in 2 queries instead of 2N.
        """
        if not users:
            return []

        user_ids = [u.id for u in users]
        counts = await self.follow_repo.get_counts_for_users(user_ids)

        return [
            PublicProfileSchema(
                id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                profile_picture=user.profile_picture,
                bio=user.bio,
                role=user.role,
                follower_count=counts.get(user.id, (0, 0))[0],
                following_count=counts.get(user.id, (0, 0))[1],
            )
            for user in users
        ]
