"""Admin service for fetching platform statistics."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import PlatformStats
from app.db.models import Application, Opportunity, Organization, User


class AdminService:
    """Service for admin dashboard operations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize admin service with database session."""
        self._db = db

    async def get_platform_stats(self) -> PlatformStats:
        """Get platform-wide statistics."""
        total_users = await self._db.scalar(select(func.count()).select_from(User).where(User.role != "organization"))
        active_users = await self._db.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True), User.role != "organization")
        )

        total_orgs = await self._db.scalar(select(func.count()).select_from(Organization))
        active_orgs = await self._db.scalar(
            select(func.count()).select_from(Organization).where(Organization.is_active.is_(True))
        )

        total_opps = await self._db.scalar(
            select(func.count()).select_from(Opportunity).where(Opportunity.deleted_at.is_(None))
        )

        total_apps = await self._db.scalar(select(func.count()).select_from(Application))
        pending_apps = await self._db.scalar(
            select(func.count()).select_from(Application).where(Application.status == "pending")
        )

        return PlatformStats(
            total_users=total_users or 0,
            total_organizations=total_orgs or 0,
            total_opportunities=total_opps or 0,
            total_applications=total_apps or 0,
            pending_applications=pending_apps or 0,
            active_users=active_users or 0,
            active_organizations=active_orgs or 0,
        )


__all__ = ["AdminService"]
