"""Service: detalhe de UM run específico de agente.

Os agregados (custo, tokens, duracao) refletem o RUN COMPLETO via SQL
aggregation. A timeline de ``calls`` é paginada via ``offset/limit`` para
evitar payloads gigantes em runs longos.

Inclui também URLs externas (Jira issue + GitHub PR search) montadas a partir
de ``Client.jira_workspace_url`` e do repo do squad — pra que o frontend
mostre links clicáveis sem precisar conhecer convenções de URL.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.schemas.agent_runs import (
    AgentRunDetail,
    ExternalCallItem,
)
from dev_autonomo.db.models import Client
from dev_autonomo.db.models.agent import AgentInstance
from dev_autonomo.db.models.cost import ExternalApiCall
from dev_autonomo.db.models.task import Task

# Limite duro pra evitar payloads gigantes mesmo se caller pedir mais
_MAX_LIMIT = 500


def _build_jira_issue_url(client: Client, key: str | None) -> str | None:
    """Monta URL pra issue Jira, ou None se a key não é Jira real."""
    if not key:
        return None
    if key.startswith(("PR-", "HIST-")):
        return None
    workspace = (client.jira_workspace_url or "").rstrip("/")
    if not workspace:
        return None
    return f"{workspace}/browse/{key}"


def _build_pr_search_url(repo_url: str | None, key: str | None) -> str | None:
    """Monta URL de busca por PRs no repo do squad que mencionam a key.

    Não persistimos mapping Task→PR ainda, então a busca por menção da key
    no title/body do PR é a forma mais robusta de encontrar o(s) PR(s).
    """
    if not repo_url or not key:
        return None
    if key.startswith("HIST-"):
        return None
    base = repo_url.rstrip("/")
    if base.endswith(".git"):
        base = base[:-4]
    # Pra chaves "PR-N" o usuário provavelmente quer ver o PR #N direto
    if key.startswith("PR-"):
        n = key[3:]
        if n.isdigit():
            return f"{base}/pull/{n}"
    return f"{base}/pulls?q=is%3Apr+{key}"


async def get_agent_run_detail(
    session: AsyncSession,
    *,
    client_id: UUID,
    agent_instance_id: UUID,
    task_id: UUID,
    offset: int = 0,
    limit: int = 100,
) -> AgentRunDetail | None:
    """Retorna o detalhe de um run específico (task_id) de um agente."""
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

    limit = max(1, min(limit, _MAX_LIMIT))

    base_where = (
        ExternalApiCall.agent_instance_id == agent_instance_id,
        ExternalApiCall.task_id == task_id,
    )

    # 2. Agregados do run completo (uma query SQL)
    agg_stmt = select(
        func.count(ExternalApiCall.id).label("calls_total"),
        func.min(ExternalApiCall.occurred_at).label("started_at"),
        func.max(ExternalApiCall.occurred_at).label("ended_at"),
        func.coalesce(func.sum(ExternalApiCall.cost_usd), Decimal("0")).label(
            "total_cost_usd"
        ),
        func.coalesce(func.sum(ExternalApiCall.input_tokens), 0).label(
            "total_input_tokens"
        ),
        func.coalesce(func.sum(ExternalApiCall.output_tokens), 0).label(
            "total_output_tokens"
        ),
        func.coalesce(
            func.sum(ExternalApiCall.cache_creation_input_tokens), 0
        ).label("total_cache_creation_tokens"),
        func.coalesce(
            func.sum(ExternalApiCall.cache_read_input_tokens), 0
        ).label("total_cache_read_tokens"),
        func.coalesce(
            func.count(ExternalApiCall.id).filter(
                ExternalApiCall.error.is_not(None)
            ),
            0,
        ).label("error_count"),
    ).where(*base_where)

    agg = (await session.execute(agg_stmt)).one()

    if agg.calls_total == 0:
        return None

    duration_ms = int((agg.ended_at - agg.started_at).total_seconds() * 1000)
    status = "failed" if agg.error_count > 0 else "completed"

    # 3. Página de calls
    calls_stmt = (
        select(ExternalApiCall)
        .where(*base_where)
        .order_by(ExternalApiCall.occurred_at.asc())
        .offset(offset)
        .limit(limit)
    )
    call_rows = (await session.execute(calls_stmt)).scalars().all()

    # 4. Task + Client (pra montar URLs externas)
    task = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    client = (
        await session.execute(select(Client).where(Client.id == client_id))
    ).scalar_one()

    # 5. URLs externas
    repo_url = _extract_first_repo_url(agent.id, task)
    jira_issue_url = _build_jira_issue_url(
        client, task.jira_issue_key if task else None
    )
    pr_search_url = _build_pr_search_url(
        repo_url, task.jira_issue_key if task else None
    )

    calls = [
        ExternalCallItem(
            id=c.id,
            occurred_at=c.occurred_at,
            provider=c.provider.value
            if hasattr(c.provider, "value")
            else str(c.provider),
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
        for c in call_rows
    ]

    return AgentRunDetail(
        task_id=task_id,
        agent_instance_id=agent_instance_id,
        title=task.title if task else None,
        jira_issue_key=task.jira_issue_key if task else None,
        jira_issue_url=jira_issue_url,
        pr_search_url=pr_search_url,
        status=status,
        started_at=agg.started_at,
        ended_at=agg.ended_at,
        duration_ms=duration_ms,
        tool_calls_count=int(agg.calls_total),
        total_cost_usd=agg.total_cost_usd,
        total_input_tokens=int(agg.total_input_tokens),
        total_output_tokens=int(agg.total_output_tokens),
        total_cache_creation_tokens=int(agg.total_cache_creation_tokens),
        total_cache_read_tokens=int(agg.total_cache_read_tokens),
        error_count=int(agg.error_count),
        calls=calls,
        calls_total=int(agg.calls_total),
        calls_offset=offset,
        calls_limit=limit,
    )


def _extract_first_repo_url(agent_id: UUID, task: Task | None) -> str | None:
    """Tenta inferir o repo principal da squad a partir do contexto disponível.

    Estratégia simples: usa o que está no demand_payload da Task (futuro)
    OU fallback hardcoded do dogfooding. Para produção real, deve vir do
    manifest da squad.
    """
    # TODO: ler de Squad.manifest_versions[latest].content.owns.repos[0]
    # Por enquanto, hardcode do dogfooding:
    return "https://github.com/rlenzi/obris-dev-squad-agent"
