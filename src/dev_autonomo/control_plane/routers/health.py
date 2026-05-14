"""Health checks: liveness simples + readiness com banco."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.dependencies import get_session

router = APIRouter(tags=["health"])

# Capturado uma vez no evento de startup do FastAPI (via set_startup_time()).
STARTUP_MONOTONIC: float = 0.0


def set_startup_time() -> None:
    """Registra o instante de startup usando time.monotonic().

    Deve ser chamado no lifespan/on_event startup do app FastAPI.
    """
    global STARTUP_MONOTONIC
    STARTUP_MONOTONIC = time.monotonic()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: o processo respondeu (sem dependencias externas)."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness: confirma conexao com Postgres."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"db unavailable: {exc}"
        ) from exc
    return {"status": "ready", "db": "ok"}


@router.get("/api/v1/health/uptime")
async def uptime() -> dict[str, int]:
    """Retorna quantos segundos o backend esta no ar desde o startup.

    Publico — sem autenticacao, mesmo nivel do /health existente.
    """
    elapsed = int(time.monotonic() - STARTUP_MONOTONIC)
    return {"uptime_seconds": elapsed}
