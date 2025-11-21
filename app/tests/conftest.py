"""Pytest configuration and fixtures for testing."""

from collections.abc import AsyncGenerator
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Test database URL (use SQLite in-memory database for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Configure anyio backend for async tests.

    Returns:
        Backend name
    """
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[object]:
    """Create test database engine.

    Yields:
        Test database engine
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(test_engine: AsyncGenerator[object]) -> AsyncGenerator[AsyncSession]:
    """Create test database session.

    Args:
        test_engine: Test database engine

    Yields:
        Test database session
    """
    # test_engine is actually an AsyncEngine, but typed as AsyncGenerator for fixture
    engine = cast("AsyncEngine", test_engine)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Create test HTTP client with database override.

    Args:
        test_db: Test database session

    Yields:
        Test HTTP client
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        """Override database dependency for testing.

        Yields:
            Test database session
        """
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
