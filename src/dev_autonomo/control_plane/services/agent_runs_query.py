"""Serviço de consulta de AgentRun para o Control Plane.

Abstrai o acesso ao banco de dados para listar execuções de agentes,
garantindo isolamento por client_id e agent_instance_id.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.schemas.agent_runs import AgentRunPublic, AgentRunsPage
from dev_autonomo.db.models import AgentInstance
from dev_autonomo.db.models.run import AgentRun


async def list_agent_runs(
    session: AsyncSession,
    *,
    client_id: UUID,
    agent_instance_id: UUID,
    offset: int = 0,
    limit: int = 50,
) -> AgentRunsPage | None:
    """Lista as execuções de um agente, paginadas.

    Verifica se o AgentInstance existe e pertence ao client_id informado.
    Retorna ``None`` se o agente não for encontrado ou não pertencer ao client.

    Args:
        session: Sessão assíncrona do SQLAlchemy.
        client_id: UUID do client que faz a requisição.
        agent_instance_id: UUID do agente cujas runs serão listadas.
        offset: Posição inicial da página (>= 0).
        limit: Tamanho máximo da página (1–200).

    Returns:
        ``AgentRunsPage`` com os itens e metadados de paginação,
        ou ``None`` se o agente não existir / não pertencer ao client.
    """
    # Valida que o agente existe e pertence ao client
    agent = (
        await session.execute(
            select(AgentInstance).where(
                AgentInstance.id == agent_instance_id,
                AgentInstance.client_id == client_id,
            )
        )
    ).scalar_one_or_none()

    if agent is None:
        return None

    # Conta o total de runs para o agente
    total: int = (
        await session.execute(
            select(func.count(AgentRun.id)).where(
                AgentRun.agent_instance_id == agent_instance_id,
                AgentRun.client_id == client_id,
            )
        )
    ).scalar_one()

    # Busca a página de runs ordenadas pela mais recente primeiro
    rows = (
        await session.execute(
            select(AgentRun)
            .where(
                AgentRun.agent_instance_id == agent_instance_id,
                AgentRun.client_id == client_id,
            )
            .order_by(AgentRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return AgentRunsPage(
        items=[AgentRunPublic.model_validate(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )
