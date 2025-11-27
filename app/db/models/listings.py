"""Listings or Events model with strict typing."""


from app.db.models.refresh_token import RefreshToken
from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Listing(Base, TimestampMixin):
    """Listings or Events model with strict typing."""

    __tablename__ = "listings"

    listing_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    date: Mapped[str] = mapped_column(Date, nullable=False)
    start_time: Mapped[str] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[str] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationship to refresh tokens
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",   
    )
