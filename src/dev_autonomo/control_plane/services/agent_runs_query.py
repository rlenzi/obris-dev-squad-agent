"""Service: query de agregação de runs por agent_instance.

Agrupa chamadas de external_api_calls por task_id para montar os "runs"
de um agente, com custo, contagem de tool calls, timestamps e status.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.schemas.agent_runs import AgentRunItem, AgentRunsPage
from dev_autonomo.db.models.agent import AgentInstance
from dev_autonomo.db.models.cost import ExternalApiCall

# Limite máximo de itens por página
_MAX_LIMIT = 200


async def list_agent_runs(
    session: AsyncSession,
    *,
    client_id: UUID,
    agent_instance_id: UUID,
    offset: int = 0,
    limit: int = 50,
) -> AgentRunsPage | None:
    """Retorna a página de runs de um agente agrupados por task_id.

    Passos:
    1. Verifica que o agent_instance_id existe e pertence ao client_id;
       retorna None se não existir (router converte em 404).
    2. Executa GROUP BY task_id em external_api_calls filtrando pelo agente.
    3. Ordena por ended_at DESC, aplica OFFSET + LIMIT (máximo _MAX_LIMIT).
    4. Executa COUNT(DISTINCT task_id) para o campo total da página.

    Returns:
        AgentRunsPage com items, total, offset e limit, ou None se o agente
        não pertencer ao client.
    """
    # 1. Verifica existência e ownership do agente
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

    # 2. Garante que limit não ultrapasse o máximo permitido
    limit = min(limit, _MAX_LIMIT)

    # Filtro base reutilizado nas duas queries
    base_where = (
        # Rows orfas (agente deletado, ondelete=SET NULL) ficam com NULL e

        # sao excluidas naturalmente por igualdade.

        ExternalApiCall.agent_instance_id == agent_instance_id,
        ExternalApiCall.task_id.is_not(None),
    )

    # 3. Query de agregação por task_id
    # status: "failed" se qualquer error IS NOT NULL, senão "completed"
    status_expr = case(
        (func.count(ExternalApiCall.error) > 0, "failed"),
        else_="completed",
    )

    aggregation_stmt = (
        select(
            ExternalApiCall.task_id.label("task_id"),
            func.count(ExternalApiCall.id).label("tool_calls_count"),
            func.coalesce(func.sum(ExternalApiCall.cost_usd), Decimal("0")).label(
                "total_cost_usd"
            ),
            func.min(ExternalApiCall.occurred_at).label("started_at"),
            func.max(ExternalApiCall.occurred_at).label("ended_at"),
            status_expr.label("status"),
        )
        .where(*base_where)
        .group_by(ExternalApiCall.task_id)
        .order_by(func.max(ExternalApiCall.occurred_at).desc())
        .offset(offset)
        .limit(limit)
    )

    rows = (await session.execute(aggregation_stmt)).all()

    # 4. Query de total (COUNT DISTINCT task_id)
    count_stmt = select(
        func.count(ExternalApiCall.task_id.distinct())
    ).where(*base_where)

    total: int = (await session.execute(count_stmt)).scalar_one()

    # 5. Busca metadata (jira_issue_key, title) das Tasks da página atual
    from dev_autonomo.db.models.task import Task as _Task

    task_ids = [row.task_id for row in rows]
    task_meta: dict = {}
    if task_ids:
        meta_rows = (
            await session.execute(
                select(
                    _Task.id, _Task.jira_issue_key, _Task.title,
                    _Task.outcome_status, _Task.outcome_iterations,
                ).where(_Task.id.in_(task_ids))
            )
        ).all()
        task_meta = {
            r.id: (r.jira_issue_key, r.title, r.outcome_status, r.outcome_iterations)
            for r in meta_rows
        }

    items = [
        AgentRunItem(
            task_id=row.task_id,
            jira_issue_key=task_meta.get(row.task_id, (None, None, None, 0))[0],
            title=task_meta.get(row.task_id, (None, None, None, 0))[1],
            tool_calls_count=row.tool_calls_count,
            total_cost_usd=row.total_cost_usd,
            started_at=row.started_at,
            ended_at=row.ended_at,
            status=row.status,
            outcome_status=(
                task_meta.get(row.task_id, (None, None, None, 0))[2].value
                if task_meta.get(row.task_id, (None, None, None, 0))[2] is not None
                else "skipped"
            ),
            outcome_iterations=task_meta.get(row.task_id, (None, None, None, 0))[3] or 0,
        )
        for row in rows
    ]

    return AgentRunsPage(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
