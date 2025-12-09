"""Base service class."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.exceptions import require

if TYPE_CHECKING:
    from app.db.repositories import BaseRepository

__all__ = ["BaseService"]


class BaseService:
    """Base class for services with database access."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session."""
        self.db = db

    async def get_or_404[T: DeclarativeBase](
        self,
        repo: BaseRepository[T],
        entity_id: UUID,
        message: str = "Not found",
    ) -> T:
        """Get entity by ID or raise 404."""
        return require(await repo.get_by_id(entity_id), message)
