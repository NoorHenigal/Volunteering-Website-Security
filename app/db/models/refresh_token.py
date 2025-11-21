"""Refresh token model with strict typing."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from datetime import datetime

    from app.db.models.user import User


class RefreshToken(Base, TimestampMixin):
    """Refresh token model with strict typing."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationship to user
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")
