"""Database models."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declarative_mixin, mapped_column, relationship

from app.core.types import ProfileVisibilityType

RoleType = Literal["volunteer", "organization", "system_admin"]
ApplicationStatusType = Literal["pending", "accepted", "rejected", "withdrawn"]


def _pg_check(expression: str, name: str) -> CheckConstraint:
    """PostgreSQL-only check constraint."""
    return CheckConstraint(expression, name=name).ddl_if(dialect="postgresql")


def _pg_index(name: str, *columns: str, where: str | None = None) -> Index:
    """PostgreSQL index with optional partial index support."""
    if where:
        return Index(name, *columns, postgresql_where=text(where)).ddl_if(dialect="postgresql")
    return Index(name, *columns)


def _user_fk() -> Mapped[UUID]:
    """User foreign key with cascade delete."""
    return mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


def _org_fk() -> Mapped[UUID]:
    """Organization foreign key with cascade delete."""
    return mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


@declarative_mixin
class IDMixin:
    """UUID primary key."""

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)


@declarative_mixin
class TimestampModelMixin:
    """Automatic created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


@declarative_mixin
class FullModelMixin(IDMixin, TimestampModelMixin):
    """UUID primary key with timestamps."""


class User(Base, FullModelMixin):
    """User account (volunteer or organization admin)."""

    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="volunteer", server_default="volunteer")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    custom_display_name: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    profile_picture: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    bio: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True, default=None)

    profile_visibility: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="public", default="public"
    )
    show_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", default=False)
    show_organizations: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1", default=True)
    searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1", default=True)

    __table_args__ = (
        CheckConstraint("role IN ('volunteer', 'organization', 'system_admin')", name="ck_user_role"),
        CheckConstraint(
            "profile_visibility IN ('public', 'authenticated', 'followers', 'private')",
            name="ck_user_profile_visibility",
        ),
        _pg_check("username ~ '^[a-zA-Z0-9_-]+$'", "ck_user_username_pattern"),
        _pg_index("ix_users_searchable", "searchable", where="searchable = true"),
        _pg_check("length(username) >= 3", "ck_user_username_length"),
        Index("ix_users_role", "role"),
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    organization_roles: Mapped[list[UserOrganizationRole]] = relationship(
        "UserOrganizationRole",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    following: Mapped[list[Follow]] = relationship(
        "Follow",
        foreign_keys="Follow.follower_id",
        back_populates="follower",
        cascade="all, delete-orphan",
    )
    followers: Mapped[list[Follow]] = relationship(
        "Follow",
        foreign_keys="Follow.followed_id",
        back_populates="followed",
        cascade="all, delete-orphan",
    )

    @property
    def display_name(self) -> str:
        """Full display name, falling back to first/last name or username."""
        if self.custom_display_name:
            return self.custom_display_name

        if self.role == "organization":
            # For organization users, we treat first_name as the full name
            return self.first_name or self.username

        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.username

    @display_name.setter
    def display_name(self, value: str | None) -> None:
        self.custom_display_name = value

    @property
    def initials(self) -> str:
        """Two-letter initials for avatar display."""
        if self.role == "organization":
            return self.first_name[:2].upper() if self.first_name else self.username[:2].upper()

        first = self.first_name[0] if self.first_name else ""
        last = self.last_name[0] if self.last_name else ""
        if first and last:
            return (first + last).upper()
        return (first or last or self.username[:2]).upper()


class RefreshToken(Base, FullModelMixin):
    """JWT refresh token for session management."""

    __tablename__ = "refresh_tokens"
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("ix_refresh_tokens_user_expires", "user_id", "expires_at"),)

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class Organization(Base, FullModelMixin):
    """Organization that posts volunteer opportunities."""

    __tablename__ = "organizations"
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    banner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        _pg_check("username ~ '^[a-zA-Z0-9_-]+$'", "ck_org_username_pattern"),
        _pg_check("length(username) >= 3", "ck_org_username_length"),
        _pg_check("length(name) >= 1", "ck_org_name_nonempty"),
    )

    opportunities: Mapped[list[Opportunity]] = relationship(
        "Opportunity",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    user_roles: Mapped[list[UserOrganizationRole]] = relationship(
        "UserOrganizationRole",
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class UserOrganizationRole(Base, FullModelMixin):
    """Links users to organizations with role (admin or member)."""

    __tablename__ = "user_organization_roles"
    user_id: Mapped[UUID] = _user_fk()
    organization_id: Mapped[UUID] = _org_fk()
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "admin", "member"

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_user_organization_role"),
        CheckConstraint("role IN ('admin', 'member')", name="ck_user_org_role"),
        Index("ix_user_org_roles_org_role", "organization_id", "role"),
    )

    user: Mapped[User] = relationship("User", back_populates="organization_roles")
    organization: Mapped[Organization] = relationship("Organization", back_populates="user_roles")


class Opportunity(Base, FullModelMixin):
    """Volunteer opportunity posted by an organization."""

    __tablename__ = "opportunities"
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(5000), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    banner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    posted_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[UUID] = _org_fk()
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    __table_args__ = (
        _pg_index("ix_opportunities_is_open", "is_open", where="is_open = true"),
        Index("ix_opportunities_org_open", "organization_id", "is_open"),
        Index("ix_opportunities_created_at", "created_at"),
        _pg_check("length(title) >= 1", "ck_opp_title_nonempty"),
        _pg_check("length(description) >= 1", "ck_opp_description_nonempty"),
    )

    poster: Mapped[User | None] = relationship("User", foreign_keys=[posted_by])
    organization: Mapped[Organization] = relationship("Organization", back_populates="opportunities")


class Application(Base, FullModelMixin):
    """Volunteer application to an opportunity."""

    __tablename__ = "applications"
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    volunteer_id: Mapped[UUID] = _user_fk()
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    __table_args__ = (
        UniqueConstraint("volunteer_id", "opportunity_id", name="uq_volunteer_opportunity"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'withdrawn')",
            name="ck_application_status",
        ),
        _pg_index("ix_applications_status_pending", "status", where="status = 'pending'"),
        Index("ix_applications_opportunity_status", "opportunity_id", "status"),
    )

    opportunity: Mapped[Opportunity] = relationship("Opportunity", foreign_keys=[opportunity_id])
    volunteer: Mapped[User] = relationship("User", foreign_keys=[volunteer_id])


class Follow(Base):
    """User-to-user follow relationship."""

    __tablename__ = "follows"

    follower_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    followed_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        CheckConstraint("follower_id != followed_id", name="ck_no_self_follow"),
        Index("ix_follows_followed_id", "followed_id"),
    )

    follower: Mapped[User] = relationship("User", foreign_keys=[follower_id], back_populates="following")
    followed: Mapped[User] = relationship("User", foreign_keys=[followed_id], back_populates="followers")


__all__ = [
    "Application",
    "ApplicationStatusType",
    "Base",
    "Follow",
    "FullModelMixin",
    "IDMixin",
    "Opportunity",
    "Organization",
    "ProfileVisibilityType",
    "RefreshToken",
    "RoleType",
    "TimestampModelMixin",
    "User",
    "UserOrganizationRole",
]
