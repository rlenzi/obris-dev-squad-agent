"""Router GET /clients/{cid}/agents/{aid}/runs e .../runs/{task_id}.

Lista paginada de runs do agente + detalhe de UM run específico.
Requer autenticação e contexto de client via ``require_client_context``.
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
    description=(
        "Retorna uma página de execuções (runs) do agente `aid` pertencente "
        "ao client `cid`. O client autenticado deve ser o dono do agente. "
        "Retorna 404 se o agente não existir ou não pertencer ao client."
    ),
)
async def list_agent_runs_endpoint(
    cid: UUID,
    aid: UUID,
    offset: int = Query(0, ge=0, description="Posição inicial da página."),
    limit: int = Query(
        50, ge=1, le=200, description="Número máximo de itens retornados (max 200)."
    ),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunsPage:
    """Endpoint principal: lista runs paginadas do agente `aid` do client `cid`."""
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
    summary="Detalhe de um run específico",
    description=(
        "Retorna agregados + timeline completa de chamadas externas para o "
        "run identificado por `task_id`. Inclui custos, tokens, latência e "
        "erros de cada chamada Claude/Voyage. Retorna 404 se o run não "
        "existir ou o agente não pertencer ao client."
    ),
)
async def get_agent_run_endpoint(
    cid: UUID,
    aid: UUID,
    task_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunDetail:
    """Endpoint de drill-down: detalhe de um run específico do agente."""
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
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="run nao encontrado ou agente nao pertence ao client",
        )

    return result
