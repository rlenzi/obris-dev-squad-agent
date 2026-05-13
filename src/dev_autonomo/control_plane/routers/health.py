"""Health checks: liveness simples + readiness com banco."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.dependencies import get_session

router = APIRouter(tags=["health"])


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
