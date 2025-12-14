"""Database repositories."""

from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, selectinload
from sqlalchemy.orm.strategy_options import _AbstractLoad

from app.db.models import Application, Follow, Opportunity, Organization, RefreshToken, User, UserOrganizationRole


class BaseRepository[T: DeclarativeBase]:
    """Generic repository providing common CRUD operations for all models."""

    model: type[T]  # Set by subclass

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def create(self, obj: T) -> T:
        """Create a new object in the database."""
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def get_by_id(self, obj_id: UUID) -> T | None:
        """Get object by ID."""
        return await self.session.get(self.model, obj_id)

    async def find_one(
        self,
        *filters: ColumnElement[bool],
        options: list[_AbstractLoad] | None = None,
    ) -> T | None:
        """Find a single entity matching filters."""
        query = select(self.model).where(*filters)
        if options:
            query = query.options(*options)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def find_many(
        self,
        *filters: ColumnElement[bool],
        options: list[_AbstractLoad] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[T]:
        """Find all entities matching filters with pagination."""
        query = select(self.model).where(*filters)
        if options:
            query = query.options(*options)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, *filters: ColumnElement[bool]) -> int:
        """Count entities matching filters."""
        query = select(func.count()).select_from(self.model).where(*filters)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, str | int | bool | UUID | None] | None = None,
    ) -> list[T]:
        """Get all objects with optional filtering and pagination."""
        query = select(self.model)
        if filters:
            for key, value in filters.items():
                query = query.where(getattr(self.model, key) == value)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(self, obj: T) -> T:
        """Update an existing object."""
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: T) -> None:
        """Delete an object from the database."""
        await self.session.delete(obj)
        await self.session.flush()


class UserRepository(BaseRepository[User]):
    """Repository for User model database operations."""

    model = User

    async def get_by_id(self, obj_id: UUID, *, include_inactive: bool = False) -> User | None:
        """Get user by ID (defaults to active-only)."""
        if include_inactive:
            return await super().get_by_id(obj_id)
        return await self.find_one(User.id == obj_id, User.is_active.is_(True))

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        return await self.find_one(User.email == email, User.is_active.is_(True))

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username."""
        return await self.find_one(User.username == username, User.is_active.is_(True))


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Repository for RefreshToken model database operations."""

    model = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """Get refresh token by token hash."""
        return await self.find_one(RefreshToken.token_hash == token_hash)


class OrganizationRepository(BaseRepository[Organization]):
    """Repository for Organization model database operations."""

    model = Organization

    async def get_by_id(self, obj_id: UUID, *, include_inactive: bool = False) -> Organization | None:
        """Get organization by ID (defaults to active-only)."""
        if include_inactive:
            return await super().get_by_id(obj_id)
        return await self.find_one(Organization.id == obj_id, Organization.is_active.is_(True))

    async def get_by_username(self, username: str) -> Organization | None:
        """Get organization by username."""
        return await self.find_one(Organization.username == username, Organization.is_active.is_(True))

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, str | int | bool | UUID | None] | None = None,
        *,
        include_inactive: bool = False,
    ) -> list[Organization]:
        """List organizations (defaults to active-only)."""
        if include_inactive:
            return await super().get_all(skip=skip, limit=limit, filters=filters)
        merged = dict(filters or {})
        merged.setdefault("is_active", True)
        return await super().get_all(skip=skip, limit=limit, filters=merged)

    async def count_all(self) -> int:
        """Count all organizations."""
        return await self.count(Organization.is_active.is_(True))

    async def get_by_id_with_opportunities(self, org_id: UUID) -> Organization | None:
        """Get organization by ID with opportunities eagerly loaded."""
        return await self.find_one(
            Organization.id == org_id,
            Organization.is_active.is_(True),
            options=[selectinload(Organization.opportunities.and_(Opportunity.deleted_at.is_(None)))],
        )

    async def create_with_admin(self, org: Organization, user_id: UUID) -> Organization:
        """Create organization and assign user as admin in one operation."""
        organization = await self.create(org)
        role = UserOrganizationRole(user_id=user_id, organization_id=organization.id, role="admin")
        self.session.add(role)
        await self.session.flush()
        return organization


class UserOrganizationRoleRepository(BaseRepository[UserOrganizationRole]):
    """Repository for UserOrganizationRole model database operations."""

    model = UserOrganizationRole

    async def get_by_user_and_org(self, user_id: UUID, organization_id: UUID) -> UserOrganizationRole | None:
        """Get user-organization role by user ID and organization ID."""
        return await self.find_one(
            UserOrganizationRole.user_id == user_id,
            UserOrganizationRole.organization_id == organization_id,
        )

    async def get_user_organizations(self, user_id: UUID) -> list[UserOrganizationRole]:
        """Get all organizations for a user."""
        return await self.find_many(UserOrganizationRole.user_id == user_id)

    async def get_user_organizations_with_org(self, user_id: UUID) -> list[UserOrganizationRole]:
        """Get all organizations for a user with organization details eagerly loaded."""
        return await self.find_many(
            UserOrganizationRole.user_id == user_id,
            options=[selectinload(UserOrganizationRole.organization)],
        )

    async def is_organization_admin(self, user_id: UUID, organization_id: UUID) -> bool:
        """Check if a user is an admin of an organization."""
        role = await self.get_by_user_and_org(user_id, organization_id)
        return role is not None and role.role == "admin"

    async def is_organization_member(self, user_id: UUID, organization_id: UUID) -> bool:
        """Check if a user is a member of an organization (any role)."""
        role = await self.get_by_user_and_org(user_id, organization_id)
        return role is not None

    async def get_members_with_users(self, organization_id: UUID) -> list[UserOrganizationRole]:
        """Get all members of an organization with user details eagerly loaded."""
        query = (
            select(UserOrganizationRole)
            .join(User, UserOrganizationRole.user_id == User.id)
            .where(UserOrganizationRole.organization_id == organization_id, User.is_active.is_(True))
            .options(selectinload(UserOrganizationRole.user))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


class OpportunityRepository(BaseRepository[Opportunity]):
    """Repository for Opportunity model database operations."""

    model = Opportunity

    async def get_by_id(self, obj_id: UUID, *, include_deleted: bool = False) -> Opportunity | None:
        """Get opportunity by ID (defaults to non-deleted only)."""
        if include_deleted:
            return await super().get_by_id(obj_id)
        return await self.find_one(Opportunity.id == obj_id, Opportunity.deleted_at.is_(None))

    async def get_all_open(self, skip: int = 0, limit: int = 100) -> list[Opportunity]:
        """Get all open opportunities with organization and poster eagerly loaded."""
        return await self.find_many(
            Opportunity.is_open.is_(True),
            Opportunity.deleted_at.is_(None),
            options=[
                selectinload(Opportunity.organization),
                selectinload(Opportunity.poster),
            ],
            skip=skip,
            limit=limit,
        )

    async def count_open(self) -> int:
        """Count all open opportunities."""
        return await self.count(Opportunity.is_open.is_(True), Opportunity.deleted_at.is_(None))

    async def get_by_id_with_organization(self, opportunity_id: UUID) -> Opportunity | None:
        """Get opportunity by ID with organization eagerly loaded."""
        return await self.find_one(
            Opportunity.id == opportunity_id,
            Opportunity.deleted_at.is_(None),
            options=[selectinload(Opportunity.organization)],
        )


class ApplicationRepository(BaseRepository[Application]):
    """Repository for Application model database operations."""

    model = Application

    async def get_by_volunteer(self, volunteer_id: UUID) -> list[Application]:
        """Get all applications for a volunteer."""
        return await self.find_many(Application.volunteer_id == volunteer_id)

    async def get_by_volunteer_with_opportunity(self, volunteer_id: UUID) -> list[Application]:
        """Get all applications for a volunteer with opportunity eagerly loaded."""
        return await self.find_many(
            Application.volunteer_id == volunteer_id,
            options=[selectinload(Application.opportunity)],
        )

    async def get_by_opportunity_with_volunteer(self, opportunity_id: UUID) -> list[Application]:
        """Get all applications for an opportunity with volunteer details eagerly loaded."""
        query = (
            select(Application)
            .join(User, Application.volunteer_id == User.id)
            .where(Application.opportunity_id == opportunity_id, User.is_active.is_(True))
            .options(selectinload(Application.volunteer))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_volunteer_and_opportunity(self, volunteer_id: UUID, opportunity_id: UUID) -> Application | None:
        """Get application by volunteer and opportunity."""
        return await self.find_one(
            Application.volunteer_id == volunteer_id,
            Application.opportunity_id == opportunity_id,
        )

    async def update_status(self, application: Application, new_status: str) -> Application:
        """Update application status."""
        application.status = new_status
        return await self.update(application)


class FollowRepository:
    """Repository for Follow model - uses composite primary key."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize FollowRepository."""
        self.session = session

    async def get_follow(self, follower_id: UUID, followed_id: UUID) -> Follow | None:
        """Get follow relationship by composite key."""
        query = select(Follow).where(
            Follow.follower_id == follower_id,
            Follow.followed_id == followed_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def is_following(self, follower_id: UUID, followed_id: UUID) -> bool:
        """Check if follow relationship exists."""
        return await self.get_follow(follower_id, followed_id) is not None

    async def get_followers(self, user_id: UUID) -> list[Follow]:
        """Get all followers of a user with follower details loaded."""
        query = (
            select(Follow)
            .join(User, Follow.follower_id == User.id)
            .where(Follow.followed_id == user_id, User.is_active.is_(True))
            .options(selectinload(Follow.follower))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_following(self, user_id: UUID) -> list[Follow]:
        """Get all users that a user follows with followed details loaded."""
        query = (
            select(Follow)
            .join(User, Follow.followed_id == User.id)
            .where(Follow.follower_id == user_id, User.is_active.is_(True))
            .options(selectinload(Follow.followed))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_follower_count(self, user_id: UUID) -> int:
        """Count followers of a user."""
        query = (
            select(func.count())
            .select_from(Follow)
            .join(User, Follow.follower_id == User.id)
            .where(Follow.followed_id == user_id, User.is_active.is_(True))
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_following_count(self, user_id: UUID) -> int:
        """Count users that a user follows."""
        query = (
            select(func.count())
            .select_from(Follow)
            .join(User, Follow.followed_id == User.id)
            .where(Follow.follower_id == user_id, User.is_active.is_(True))
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def create_follow(self, follower_id: UUID, followed_id: UUID) -> Follow:
        """Create a follow relationship."""
        follow = Follow(follower_id=follower_id, followed_id=followed_id)
        self.session.add(follow)
        await self.session.flush()
        return follow

    async def delete_follow(self, follower_id: UUID, followed_id: UUID) -> None:
        """Delete a follow relationship (idempotent)."""
        follow = await self.get_follow(follower_id, followed_id)
        if follow:
            await self.session.delete(follow)
            await self.session.flush()

    async def get_counts_for_users(self, user_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
        """Batch fetch follower and following counts for multiple users.

        Returns dict mapping user_id --> (follower_count, following_count).
        This eliminates N+1 queries when building profile lists.
        """
        if not user_ids:
            return {}

        # Get follower counts (users following each user_id)
        follower_query = (
            select(Follow.followed_id, func.count())
            .join(User, Follow.follower_id == User.id)
            .where(Follow.followed_id.in_(user_ids))
            .where(User.is_active.is_(True))
            .group_by(Follow.followed_id)
        )
        follower_result = await self.session.execute(follower_query)
        follower_counts: dict[UUID, int] = {row[0]: row[1] for row in follower_result.all()}

        # Get following counts (users each user_id follows)
        following_query = (
            select(Follow.follower_id, func.count())
            .join(User, Follow.followed_id == User.id)
            .where(Follow.follower_id.in_(user_ids))
            .where(User.is_active.is_(True))
            .group_by(Follow.follower_id)
        )
        following_result = await self.session.execute(following_query)
        following_counts: dict[UUID, int] = {row[0]: row[1] for row in following_result.all()}

        # Combine into result dict
        return {uid: (follower_counts.get(uid, 0), following_counts.get(uid, 0)) for uid in user_ids}


__all__ = [
    "ApplicationRepository",
    "FollowRepository",
    "OpportunityRepository",
    "OrganizationRepository",
    "RefreshTokenRepository",
    "UserOrganizationRoleRepository",
    "UserRepository",
]
