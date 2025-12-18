"""Report schemas for content moderation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.core.base_schemas import BaseCreate, BaseOut, StrictModel
from app.db.models import ReportStatusType, ReportTargetType

REPORT_REASONS: list[tuple[str, str]] = [
    ("spam", "Spam or misleading content"),
    ("harassment", "Harassment or bullying"),
    ("inappropriate", "Inappropriate content"),
    ("impersonation", "Impersonation"),
    ("other", "Other"),
]


class ReportCreate(BaseCreate):
    """Schema for creating a report."""

    target_type: ReportTargetType
    target_id: UUID
    reason: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class ReportOut(BaseOut):
    """Report response schema."""

    reporter_id: UUID
    target_type: ReportTargetType
    target_id: UUID | None
    reason: str
    description: str | None
    status: ReportStatusType
    resolved_at: datetime | None
    resolved_by_id: UUID | None


class ReportResolve(BaseCreate):
    """Schema for resolving a report."""

    action: Literal["delete", "reject"]


class ReportListItem(StrictModel):
    """Report item for list display."""

    id: UUID
    reporter_username: str
    reporter_display_name: str
    target_type: ReportTargetType
    target_display_name: str
    target_id: UUID | None
    reason: str
    description: str | None
    status: ReportStatusType
    created_at: datetime


__all__ = [
    "REPORT_REASONS",
    "ReportCreate",
    "ReportListItem",
    "ReportOut",
    "ReportResolve",
]
