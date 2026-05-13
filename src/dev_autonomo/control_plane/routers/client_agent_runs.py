"""Router GET /clients/{cid}/agents/{aid}/runs e .../runs/{task_id}.

Lista paginada de runs do agente + detalhe (com timeline de chamadas paginada).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.agent_runs import (
    AgentRunDetail,
    AgentRunsPage,
)
from dev_autonomo.control_plane.services.agent_run_detail import (
    get_agent_run_detail,
)
from dev_autonomo.control_plane.services.agent_runs_query import list_agent_runs
from dev_autonomo.db.models import Client

router = APIRouter(tags=["client / agent runs"])


@router.get(
    "/clients/{cid}/agents/{aid}/runs",
    response_model=AgentRunsPage,
    summary="Lista execuções de um agente",
)
async def list_agent_runs_endpoint(
    cid: UUID,
    aid: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunsPage:
    """Lista runs paginadas do agente `aid` do client `cid`."""
    client, _ = ctx

    if client.id != cid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="client autenticado nao corresponde ao cid informado na URL",
        )

    result = await list_agent_runs(
        session,
        client_id=cid,
        agent_instance_id=aid,
        offset=offset,
        limit=limit,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agente nao encontrado ou nao pertence ao client",
        )

    return result


@router.get(
    "/clients/{cid}/agents/{aid}/runs/{task_id}",
    response_model=AgentRunDetail,
    summary="Detalhe de um run específico (timeline paginada)",
    description=(
        "Retorna agregados + janela paginada de chamadas externas para o run "
        "`task_id`. Os totais (custo, tokens, error_count) refletem o RUN "
        "COMPLETO, mas a lista `calls` é restrita a `[offset, offset+limit)`. "
        "`calls_total` indica o total disponível para paginar no frontend."
    ),
)
async def get_agent_run_endpoint(
    cid: UUID,
    aid: UUID,
    task_id: UUID,
    offset: int = Query(0, ge=0, description="Início da janela de calls."),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Tamanho da janela de calls (max 500).",
    ),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunDetail:
    """Drill-down: detalhe de um run específico com timeline paginada."""
    client, _ = ctx

    if client.id != cid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="client autenticado nao corresponde ao cid informado na URL",
        )

    result = await get_agent_run_detail(
        session,
        client_id=cid,
        agent_instance_id=aid,
        task_id=task_id,
        offset=offset,
        limit=limit,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="run nao encontrado ou agente nao pertence ao client",
        )

    return result
