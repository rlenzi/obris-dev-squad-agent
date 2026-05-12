"""Engine async e session factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from dev_autonomo.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_async_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=_settings.ENVIRONMENT == "local",
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager para workers e scripts (commit/rollback automatico)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency injection do FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session
