"""SQLAlchemy models with strict typing."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declarative_mixin, mapped_column, relationship

from app.core.types import ProfileVisibilityType

# Type Aliases
RoleType = Literal["admin", "volunteer", "organization"]
ApplicationStatusType = Literal["pending", "accepted", "rejected", "withdrawn"]


# Column Helpers
def _user_fk() -> Mapped[UUID]:
    """Create a user foreign key column."""
    return mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


def _org_fk() -> Mapped[UUID]:
    """Create an organization foreign key column."""
    return mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


# Base Class
class Base(DeclarativeBase):
    """Base class for all database models."""


# Mixins
@declarative_mixin
class IDMixin:
    """Mixin for primary key ID column using UUID."""

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)


@declarative_mixin
class TimestampModelMixin:
    """Mixin for created_at and updated_at timestamp columns."""

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
    """Combines ID and timestamp mixins for complete base model."""


# Models
class User(Base, FullModelMixin):
    """User model with strict typing."""

    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    profile_picture: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    bio: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    profile_visibility: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="public", default="public"
    )
    show_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", default=False)
    show_organizations: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1", default=True)
    searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1", default=True)

    # Relationship to refresh tokens
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Relationship to organization roles
    organization_roles: Mapped[list[UserOrganizationRole]] = relationship(
        "UserOrganizationRole",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Follow relationships
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


class RefreshToken(Base, FullModelMixin):
    """Refresh token model with strict typing."""

    __tablename__ = "refresh_tokens"
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship to user
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class Organization(Base, FullModelMixin):
    """Organization model with strict typing."""

    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Relationships
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
    """User-Organization relationship model with strict typing."""

    __tablename__ = "user_organization_roles"
    user_id: Mapped[UUID] = _user_fk()
    organization_id: Mapped[UUID] = _org_fk()
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "admin", "member"

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="organization_roles")
    organization: Mapped[Organization] = relationship("Organization", back_populates="user_roles")


class Opportunity(Base, FullModelMixin):
    """Opportunity model with strict typing."""

    __tablename__ = "opportunities"
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    posted_by: Mapped[UUID] = _user_fk()
    organization_id: Mapped[UUID] = _org_fk()
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    # Relationships
    poster: Mapped[User] = relationship("User", foreign_keys=[posted_by])
    organization: Mapped[Organization] = relationship("Organization", back_populates="opportunities")


class Application(Base, FullModelMixin):
    """Application model with strict typing."""

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
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    opportunity: Mapped[Opportunity] = relationship("Opportunity", foreign_keys=[opportunity_id])
    volunteer: Mapped[User] = relationship("User", foreign_keys=[volunteer_id])


class Follow(Base):
    """User follow relationship - uses composite primary key."""

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

    # Relationships
    follower: Mapped[User] = relationship("User", foreign_keys=[follower_id], back_populates="following")
    followed: Mapped[User] = relationship("User", foreign_keys=[followed_id], back_populates="followers")


# Exports
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
