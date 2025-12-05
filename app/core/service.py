"""Base service class for shared service patterns."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.exceptions import require

if TYPE_CHECKING:
    from app.db.repositories import BaseRepository

__all__ = ["BaseService"]


class BaseService:
    """Base class for all service classes.

    Provides common initialization pattern with database session.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def get_or_404[T: DeclarativeBase](
        self,
        repo: BaseRepository[T],
        entity_id: UUID,
        message: str = "Not found",
    ) -> T:
        """Get entity by ID or raise 404.

        Args:
            repo: Repository instance to use for lookup
            entity_id: UUID of the entity to find
            message: Error message if not found

        Returns:
            The found entity

        Raises:
            HTTPException: 404 if entity not found
        """
        return require(await repo.get_by_id(entity_id), message)
