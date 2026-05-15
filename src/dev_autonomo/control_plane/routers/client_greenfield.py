"""Router /client/squads/{id}/greenfield/* — Cenário B do redesign (S-1)."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session, require_client_context,
)
from dev_autonomo.db.models import Client, Squad
from dev_autonomo.onboarding import analyzer as oa_v2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client/squads", tags=["client / greenfield"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RunGreenfieldRequest(BaseModel):
    """POST /run-greenfield-analysis body."""

    description: str = Field(
        ..., min_length=50, max_length=5000,
        description="Texto livre do cliente descrevendo o projeto",
    )


class RunGreenfieldResponse(BaseModel):
    task_id: UUID
    status: str  # "started" | "already_running"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_client_admin(role: UserRole) -> None:
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="apenas CLIENT_ADMIN.",
        )


async def _resolve_squad(
    session: AsyncSession, client: Client, squad_id: UUID,
) -> Squad:
    squad = (await session.execute(
        select(Squad).where(Squad.id == squad_id, Squad.client_id == client.id)
    )).scalar_one_or_none()
    if squad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="squad nao encontrada")
    return squad


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{squad_id}/run-greenfield-analysis",
    response_model=RunGreenfieldResponse,
)
async def run_greenfield_analysis(
    squad_id: UUID,
    body: RunGreenfieldRequest,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> RunGreenfieldResponse:
    """Dispara análise greenfield (cenário B) em background.

    Idempotente: se ja existe analise IN_PROGRESS pra squad, retorna o
    task_id existente. Greenfield não tem clone/scan/grader — chamada
    direta Claude pra propor stack + agentes baseado na descrição.
    """
    client, role = ctx
    _require_client_admin(role)
    squad = await _resolve_squad(session, client, squad_id)

    existing = await oa_v2._find_active_onboarding_task(session, squad.id)
    already = existing is not None

    try:
        task_id = await oa_v2.start_greenfield_analysis(
            session, client=client, squad=squad,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await session.commit()

    return RunGreenfieldResponse(
        task_id=task_id,
        status="already_running" if already else "started",
    )
