"""Profile service for managing user profiles and follow functionality."""

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import require
from app.core.service import BaseService
from app.db.models import Follow, User
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
        """Initialize ProfileService with database session."""
        super().__init__(db)
        self.user_repo = UserRepository(db)
        self.follow_repo = FollowRepository(db)

    async def get_profile(
        self,
        username: str,
        viewer: User | None,
    ) -> PublicProfileSchema | FullProfileSchema:
        """Get user profile with appropriate visibility based on viewer relationship.

        Args:
            username: Username of the profile to view
            viewer: Currently authenticated user (or None for anonymous)

        Returns:
            PublicProfileSchema or FullProfileSchema based on privacy settings

        Raises:
            HTTPException: 404 if user not found, 403 if profile is private
        """
        profile_user = require(await self.user_repo.get_by_username(username), "User not found")

        # Check if viewer can see full profile
        can_view_full = await self._can_view_full_profile(profile_user, viewer)

        if not can_view_full:
            # Check if profile is completely private
            if profile_user.profile_visibility == "private" and (viewer is None or viewer.id != profile_user.id):
                raise HTTPException(status_code=403, detail="This profile is private")

            # Return public profile only (counts calculated in _to_public_profile)
            return await self._to_public_profile(profile_user)

        # Build full profile - calculate counts only when needed
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
        """Check if viewer can see full profile based on privacy settings.

        Args:
            profile_user: User whose profile is being viewed
            viewer: Currently authenticated user (or None)

        Returns:
            True if viewer can see full profile
        """
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
        """Update user's bio and description.

        Args:
            user: User to update
            data: Profile update data

        Returns:
            Updated user
        """
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(user, field, value)

        return await self.user_repo.update(user)

    async def update_privacy_settings(self, user: User, data: PrivacySettingsSchema) -> User:
        """Update user's privacy settings.

        Args:
            user: User to update
            data: Privacy settings data

        Returns:
            Updated user
        """
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            # Skip null values - don't overwrite existing settings with null
            if value is not None:
                setattr(user, field, value)

        return await self.user_repo.update(user)

    async def follow_user(self, follower: User, followed_username: str) -> Follow:
        """Create follow relationship.

        Args:
            follower: User who wants to follow
            followed_username: Username of user to follow

        Returns:
            Created Follow relationship

        Raises:
            HTTPException: 404 if user not found, 400 if invalid operation
        """
        followed = require(await self.user_repo.get_by_username(followed_username), "User not found")

        if follower.id == followed.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot follow yourself")

        # Check if already following
        existing = await self.follow_repo.get_follow(follower.id, followed.id)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following this user")

        return await self.follow_repo.create_follow(follower.id, followed.id)

    async def unfollow_user(self, follower: User, followed_username: str) -> None:
        """Remove follow relationship (idempotent).

        Args:
            follower: User who wants to unfollow
            followed_username: Username of user to unfollow

        Raises:
            HTTPException: 404 if user not found
        """
        followed = require(await self.user_repo.get_by_username(followed_username), "User not found")

        await self.follow_repo.delete_follow(follower.id, followed.id)

    async def get_followers(
        self,
        username: str,
        viewer: User | None,
    ) -> list[PublicProfileSchema]:
        """Get list of followers for a user.

        Args:
            username: Username of the user
            viewer: Currently authenticated user (or None)

        Returns:
            List of follower profiles

        Raises:
            HTTPException: 404 if user not found
        """
        user = require(await self.user_repo.get_by_username(username), "User not found")

        if not await self._can_view_followers(user, viewer):
            return []

        follows = await self.follow_repo.get_followers(user.id)
        return [await self._to_public_profile(f.follower) for f in follows]

    async def get_following(
        self,
        username: str,
        viewer: User | None,
    ) -> list[PublicProfileSchema]:
        """Get list of users that a user follows.

        Args:
            username: Username of the user
            viewer: Currently authenticated user (or None)

        Returns:
            List of followed user profiles

        Raises:
            HTTPException: 404 if user not found
        """
        user = require(await self.user_repo.get_by_username(username), "User not found")

        if not await self._can_view_followers(user, viewer):
            return []

        follows = await self.follow_repo.get_following(user.id)
        return [await self._to_public_profile(f.followed) for f in follows]

    async def _can_view_followers(self, user: User, viewer: User | None) -> bool:
        """Check if viewer can see user's followers/following lists.

        Args:
            user: User whose lists are being viewed
            viewer: Currently authenticated user (or None)

        Returns:
            True if viewer can see the lists
        """
        # Owner can always see their own lists
        if viewer and viewer.id == user.id:
            return True

        # For now, follow the same rules as profile visibility
        return await self._can_view_full_profile(user, viewer)

    async def _to_public_profile(self, user: User) -> PublicProfileSchema:
        """Convert User to PublicProfileSchema.

        Args:
            user: User to convert

        Returns:
            PublicProfileSchema
        """
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
