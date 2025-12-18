"""Database models."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declarative_mixin, mapped_column, relationship

from app.core.services.encryption import decrypt_field
from app.core.types import ProfileVisibilityType

RoleType = Literal["volunteer", "organization", "system_admin"]
ApplicationStatusType = Literal["pending", "accepted", "rejected", "withdrawn"]
ParticipantType = Literal["user", "organization"]


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


def _demo_seed_fk(*, index: bool = True) -> Mapped[UUID | None]:
    """Optional DemoSeedRun foreign key used to tag demo-created rows."""
    return mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("demo_seed_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=index,
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


class DemoSeedRun(Base, FullModelMixin):
    """Tracks an active demo seed run so demo data can be managed safely."""

    __tablename__ = "demo_seed_runs"

    namespace: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    __table_args__ = (
        Index(
            "ux_demo_seed_runs_one_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ).ddl_if(dialect="postgresql"),
    )


class User(Base, FullModelMixin):
    """User account (volunteer or organization admin)."""

    __tablename__ = "users"
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()
    email_ciphertext: Mapped[str] = mapped_column(String(512), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="volunteer", server_default="volunteer")
    ip_address_ciphertext: Mapped[str | None] = mapped_column(String(512), nullable=True)
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
        _pg_index("ix_users_is_active", "is_active", where="is_active = true"),
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
    def email(self) -> str:
        """Decrypt and return email for display purposes."""
        return decrypt_field(self.email_ciphertext) or ""

    @property
    def ip_address(self) -> str | None:
        """Decrypt and return IP address for display purposes."""
        return decrypt_field(self.ip_address_ciphertext)

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
    device_info_ciphertext: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (Index("ix_refresh_tokens_user_expires", "user_id", "expires_at"),)

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")

    @property
    def device_info(self) -> str | None:
        """Decrypt and return device info for display purposes."""
        return decrypt_field(self.device_info_ciphertext)


class Organization(Base, FullModelMixin):
    """Organization that posts volunteer opportunities."""

    __tablename__ = "organizations"
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    banner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        _pg_check("username ~ '^[a-zA-Z0-9_-]+$'", "ck_org_username_pattern"),
        _pg_check("length(username) >= 3", "ck_org_username_length"),
        _pg_check("length(name) >= 1", "ck_org_name_nonempty"),
        _pg_index("ix_organizations_is_active", "is_active", where="is_active = true"),
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
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()
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
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(5000), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    banner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
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
        _pg_index("ix_opportunities_not_deleted", "deleted_at", where="deleted_at IS NULL"),
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
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()
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
    message_ciphertext: Mapped[str | None] = mapped_column(String(2048), nullable=True)

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

    @property
    def message(self) -> str | None:
        """Decrypt and return message for display purposes."""
        return decrypt_field(self.message_ciphertext)


class Follow(Base):
    """User-to-user follow relationship."""

    __tablename__ = "follows"

    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk(index=False)

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


class Conversation(Base, FullModelMixin):
    """A DM conversation between two participants (user/org/org-org)."""

    __tablename__ = "conversations"
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()

    dm_key: Mapped[str] = mapped_column(String(192), unique=True, nullable=False, index=True)

    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        Index(
            "ix_conversations_last_message_at_nulls_last",
            last_message_at.desc().nulls_last(),
        ).ddl_if(dialect="postgresql"),
    )

    participants: Mapped[list[ConversationParticipant]] = relationship(
        "ConversationParticipant",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at.desc()",
    )


class ConversationParticipant(Base, FullModelMixin):
    """Links a user or organization to a conversation."""

    __tablename__ = "conversation_participants"
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        _pg_check(
            "(user_id IS NOT NULL AND organization_id IS NULL) OR (user_id IS NULL AND organization_id IS NOT NULL)",
            "ck_participant_one_entity",
        ),
        UniqueConstraint("conversation_id", "user_id", name="uq_conv_user"),
        UniqueConstraint("conversation_id", "organization_id", name="uq_conv_org"),
        Index("ix_conv_participants_user", "user_id", "conversation_id"),
        Index("ix_conv_participants_org", "organization_id", "conversation_id"),
    )

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="participants")
    user: Mapped[User | None] = relationship("User", foreign_keys=[user_id])
    organization: Mapped[Organization | None] = relationship("Organization", foreign_keys=[organization_id])

    @property
    def participant_type(self) -> ParticipantType:
        """Return the type of participant."""
        return "user" if self.user_id else "organization"

    @property
    def entity_id(self) -> UUID:
        """Return the ID of the participant entity."""
        return self.user_id if self.user_id else self.organization_id  # type: ignore[return-value]

    @property
    def has_unread(self) -> bool:
        """Check if there are unread messages (O(1) boolean check)."""
        if not self.conversation.last_message_at:
            return False
        if not self.last_read_at:
            return True
        return self.conversation.last_message_at > self.last_read_at


class Message(Base, FullModelMixin):
    """A message within a conversation."""

    __tablename__ = "messages"
    demo_seed_run_id: Mapped[UUID | None] = _demo_seed_fk()

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sender_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sender_organization_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    content_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        _pg_check(
            "(sender_user_id IS NOT NULL AND sender_organization_id IS NULL) OR "
            "(sender_user_id IS NULL AND sender_organization_id IS NOT NULL)",
            "ck_message_one_sender",
        ),
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
        Index("ix_messages_conv_created_id", "conversation_id", "created_at", "id"),
    )

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")
    sender_user: Mapped[User | None] = relationship("User", foreign_keys=[sender_user_id])
    sender_organization: Mapped[Organization | None] = relationship(
        "Organization", foreign_keys=[sender_organization_id]
    )

    @property
    def content(self) -> str:
        """Decrypt and return message content."""
        return decrypt_field(self.content_ciphertext) or ""

    @property
    def sender_type(self) -> ParticipantType:
        """Return the type of sender."""
        return "user" if self.sender_user_id else "organization"

    @property
    def sender_id(self) -> UUID:
        """Return the ID of the sender entity."""
        return self.sender_user_id if self.sender_user_id else self.sender_organization_id  # type: ignore[return-value]


__all__ = [
    "Application",
    "ApplicationStatusType",
    "Base",
    "Conversation",
    "ConversationParticipant",
    "DemoSeedRun",
    "Follow",
    "FullModelMixin",
    "IDMixin",
    "Message",
    "Opportunity",
    "Organization",
    "ParticipantType",
    "ProfileVisibilityType",
    "RefreshToken",
    "RoleType",
    "TimestampModelMixin",
    "User",
    "UserOrganizationRole",
]
