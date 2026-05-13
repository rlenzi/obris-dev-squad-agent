"""Service: detalhe de UM run específico de agente.

Retorna agregados + timeline completa de chamadas externas (Anthropic/Voyage).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.schemas.agent_runs import (
    AgentRunDetail,
    ExternalCallItem,
)
from dev_autonomo.db.models.agent import AgentInstance
from dev_autonomo.db.models.cost import ExternalApiCall
from dev_autonomo.db.models.task import Task


async def get_agent_run_detail(
    session: AsyncSession,
    *,
    client_id: UUID,
    agent_instance_id: UUID,
    task_id: UUID,
) -> AgentRunDetail | None:
    """Retorna o detalhe de um run específico (task_id) de um agente.

    Returns:
        AgentRunDetail se o run existe e pertence ao client+agente.
        None se o agente não pertence ao client, ou se o run não tem calls.
    """
    # 1. Ownership do agente
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

    # 2. Busca todas as calls do run, ordenadas por timestamp
    calls_rows = (
        await session.execute(
            select(ExternalApiCall)
            .where(
                ExternalApiCall.agent_instance_id == agent_instance_id,
                ExternalApiCall.task_id == task_id,
            )
            .order_by(ExternalApiCall.occurred_at.asc())
        )
    ).scalars().all()

    if not calls_rows:
        return None

    # 3. Task metadata (opcional — pode não existir mais)
    task = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()

    # 4. Agregados
    started_at = calls_rows[0].occurred_at
    ended_at = calls_rows[-1].occurred_at
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    total_cost = sum(
        (c.cost_usd for c in calls_rows), start=Decimal("0")
    )
    total_in = sum(c.input_tokens or 0 for c in calls_rows)
    total_out = sum(c.output_tokens or 0 for c in calls_rows)
    total_cache_creation = sum(
        c.cache_creation_input_tokens or 0 for c in calls_rows
    )
    total_cache_read = sum(c.cache_read_input_tokens or 0 for c in calls_rows)
    error_count = sum(1 for c in calls_rows if c.error)
    status = "failed" if error_count > 0 else "completed"

    calls = [
        ExternalCallItem(
            id=c.id,
            occurred_at=c.occurred_at,
            provider=c.provider.value if hasattr(c.provider, "value") else str(c.provider),
            kind=c.kind.value if hasattr(c.kind, "value") else str(c.kind),
            model=c.model,
            input_tokens=c.input_tokens or 0,
            output_tokens=c.output_tokens or 0,
            cache_creation_input_tokens=c.cache_creation_input_tokens or 0,
            cache_read_input_tokens=c.cache_read_input_tokens or 0,
            cost_usd=c.cost_usd,
            latency_ms=c.latency_ms,
            request_id=c.request_id,
            error=c.error,
        )
        for c in calls_rows
    ]

    return AgentRunDetail(
        task_id=task_id,
        agent_instance_id=agent_instance_id,
        title=task.title if task else None,
        jira_issue_key=task.jira_issue_key if task else None,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        tool_calls_count=len(calls_rows),
        total_cost_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cache_creation_tokens=total_cache_creation,
        total_cache_read_tokens=total_cache_read,
        error_count=error_count,
        calls=calls,
    )
