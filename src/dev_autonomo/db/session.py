"""Engine async e session factory."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dev_autonomo.config import get_settings

_settings = get_settings()

# Em testes, desativamos o pool: cada sessao abre/fecha conexao isolada,
# evitando conexoes orfaãs entre event loops do pytest-asyncio.
_TESTING = os.getenv("DEV_AUTONOMO_TESTING") == "1"
_pool_kwargs: dict[str, Any] = (
    {"poolclass": NullPool}
    if _TESTING
    else {"pool_size": 5, "max_overflow": 10}
)

engine = create_async_engine(
    _settings.database_async_url,
    pool_pre_ping=True,
    echo=(not _TESTING) and _settings.ENVIRONMENT == "local",
    **_pool_kwargs,
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
