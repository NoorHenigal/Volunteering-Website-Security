"""Report service for content moderation."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Opportunity, Organization, Report, ReportTargetType, User
from app.db.repositories import (
    MessageRepository,
    OpportunityRepository,
    OrganizationRepository,
    ReportRepository,
    UserRepository,
)
from app.reports.schemas import ReportListItem


class ReportService:
    """Service for report operations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize report service with database session."""
        self._db = db
        self._repo = ReportRepository(db)

    async def create_report(
        self,
        reporter_id: UUID,
        target_type: ReportTargetType,
        target_id: UUID,
        reason: str,
        description: str | None = None,
    ) -> Report:
        """Create a new report."""
        if await self._repo.exists_for_target(reporter_id, target_type, target_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already reported this content",
            )

        await self._validate_target_exists(target_type, target_id)

        report = Report(
            reporter_id=reporter_id,
            target_type=target_type,
            reason=reason,
            description=description,
        )

        self._set_target_id(report, target_type, target_id)

        return await self._repo.create(report)

    def _set_target_id(self, report: Report, target_type: ReportTargetType, target_id: UUID) -> None:
        """Set the appropriate target ID field based on target type."""
        target_field_map: dict[ReportTargetType, str] = {
            "user": "target_user_id",
            "organization": "target_organization_id",
            "opportunity": "target_opportunity_id",
            "message": "target_message_id",
        }
        setattr(report, target_field_map[target_type], target_id)

    async def _validate_target_exists(self, target_type: ReportTargetType, target_id: UUID) -> None:
        """Validate that the target exists."""
        target_exists = False

        if target_type == "user":
            user = await UserRepository(self._db).get_by_id(target_id)
            target_exists = user is not None
        elif target_type == "organization":
            org = await OrganizationRepository(self._db).get_by_id(target_id)
            target_exists = org is not None
        elif target_type == "opportunity":
            opp = await OpportunityRepository(self._db).get_by_id(target_id)
            target_exists = opp is not None
        elif target_type == "message":
            msg = await MessageRepository(self._db).get_by_id(target_id)
            target_exists = msg is not None

        if not target_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{target_type.capitalize()} not found",
            )

    async def get_pending_reports(self, page: int = 1, limit: int = 20) -> tuple[list[ReportListItem], int]:
        """Get pending reports for admin review."""
        skip = (page - 1) * limit
        reports = await self._repo.get_pending(skip=skip, limit=limit)
        total = await self._repo.count_pending()

        items = [
            ReportListItem(
                id=r.id,
                reporter_username=r.reporter.username,
                reporter_display_name=r.reporter.display_name,
                target_type=r.target_type,  # type: ignore[arg-type]
                target_display_name=r.target_display_name,
                target_id=r.target_id,
                reason=r.reason,
                description=r.description,
                status=r.status,  # type: ignore[arg-type]
                created_at=r.created_at,
            )
            for r in reports
        ]

        return items, total

    async def get_report_by_id(self, report_id: UUID) -> Report:
        """Get report by ID with all details."""
        report = await self._repo.get_by_id_with_details(report_id)
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )
        return report

    async def resolve_report(
        self,
        report_id: UUID,
        admin_id: UUID,
        action: str,
    ) -> Report:
        """Resolve a report by deleting content or rejecting the report."""
        report = await self.get_report_by_id(report_id)

        if report.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report has already been resolved",
            )

        if action == "delete":
            await self._delete_target(report)
            report.status = "resolved_deleted"
        elif action == "reject":
            report.status = "rejected"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid action",
            )

        report.resolved_at = datetime.now(UTC)
        report.resolved_by_id = admin_id

        return await self._repo.update(report)

    async def _delete_target(self, report: Report) -> None:
        """Soft-delete the reported content based on target type."""
        if report.target_type == "user" and report.target_user:
            await self._soft_delete_user(report.target_user)
        elif report.target_type == "organization" and report.target_organization:
            await self._soft_delete_organization(report.target_organization)
        elif report.target_type == "opportunity" and report.target_opportunity:
            await self._soft_delete_opportunity(report.target_opportunity)
        elif report.target_type == "message" and report.target_message:
            await self._delete_message(report.target_message)

    async def _soft_delete_user(self, user: User) -> None:
        """Soft-delete a user by setting is_active to False."""
        user.is_active = False
        await self._db.flush()

    async def _soft_delete_organization(self, org: Organization) -> None:
        """Soft-delete an organization by setting is_active to False."""
        org.is_active = False
        await self._db.flush()

    async def _soft_delete_opportunity(self, opp: Opportunity) -> None:
        """Soft-delete an opportunity by setting deleted_at."""
        opp.deleted_at = datetime.now(UTC)
        await self._db.flush()

    async def _delete_message(self, msg: Message) -> None:
        """Delete a message (hard delete since messages don't have soft-delete)."""
        await self._db.delete(msg)
        await self._db.flush()

    async def count_pending(self) -> int:
        """Count pending reports."""
        return await self._repo.count_pending()


__all__ = ["ReportService"]
