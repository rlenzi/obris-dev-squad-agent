"""Dispara um agente como subprocess detached.

V1 minimo: roda `uv run python -m scripts.dev.run_<tier>_task <ISSUE>` em
background via setsid, log em /tmp/run-<task_id>.log. Sem fila/worker —
o subprocess sobrevive o request HTTP.

Quando subir o consumer RabbitMQ real (Fase 2.x), trocar este modulo
para apenas publicar mensagem na fila.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import AgentTier
from dev_autonomo.db.models import AgentInstance, Client, Task

logger = logging.getLogger(__name__)

# Mapeia tier do agente -> nome do modulo runner em scripts/dev/
TIER_RUNNER: dict[AgentTier, str] = {
    AgentTier.BA: "scripts.dev.run_ba_task",
    AgentTier.ARCHITECT: "scripts.dev.run_architect_task",
    AgentTier.DEV: "scripts.dev.run_platform_task",
    AgentTier.REVIEWER: "scripts.dev.run_reviewer_task",
    # Onboarding Analyst recebe repo_path, nao issue_key — sem trigger generico
}

# Diretorio raiz do repo da plataforma (cwd do subprocess).
# Configuravel por env var pra subir em outra maquina sem hardcode.
DEFAULT_REPO_ROOT = Path(
    os.environ.get(
        "DEV_AUTONOMO_REPO_ROOT",
        "/home/rubens/dev-autonomo-workspace/dev-autonomo",
    )
)
LOG_DIR = Path(os.environ.get("DEV_AUTONOMO_RUN_LOG_DIR", "/tmp"))


class TriggerError(Exception):
    """Erro funcional do trigger (tier sem runner, agent invalido, etc)."""


async def trigger_agent_run(
    *,
    session: AsyncSession,
    client: Client,
    agent_id: UUID,
    jira_issue_key: str,
) -> dict[str, object]:
    """Cria Task local + dispara subprocess detached que roda o agente.

    Retorna dict com ``task_id``, ``jira_issue_key``, ``agent_id``, ``tier``,
    ``pid``, ``log_path``.
    """
    agent = (
        await session.execute(
            select(AgentInstance).where(
                AgentInstance.id == agent_id,
                AgentInstance.client_id == client.id,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise TriggerError(f"agente {agent_id} nao encontrado no cliente.")

    tier = AgentTier(agent.domain_business)
    runner_module = TIER_RUNNER.get(tier)
    if runner_module is None:
        raise TriggerError(
            f"tier {tier.value!r} nao suporta trigger generico via painel. "
            f"Use o runner CLI especifico (ex: Onboarding Analyst exige "
            f"repo_path em vez de issue_key)."
        )

    # Cria/recupera Task local (idempotente por jira_issue_key)
    workspace_url = client.jira_workspace_url
    existing = (
        await session.execute(
            select(Task).where(
                Task.client_id == client.id,
                Task.jira_workspace_url == workspace_url,
                Task.jira_issue_key == jira_issue_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        task = existing
        if task.assigned_agent_id != agent.id:
            task.assigned_agent_id = agent.id
    else:
        task = Task(
            client_id=client.id,
            squad_id=agent.squad_id,
            jira_workspace_url=workspace_url,
            jira_issue_key=jira_issue_key,
            title=f"Issue {jira_issue_key}",
            assigned_agent_id=agent.id,
        )
        session.add(task)
        await session.flush()

    await session.commit()

    # Loga no arquivo nomeado pela Task — facilita correlacao
    log_path = LOG_DIR / f"run-{task.id}.log"

    if not DEFAULT_REPO_ROOT.exists():
        raise TriggerError(
            f"repo root nao existe: {DEFAULT_REPO_ROOT}. Defina "
            f"DEV_AUTONOMO_REPO_ROOT na env do uvicorn."
        )

    # subprocess detached via setsid — sobrevive ao processo do uvicorn.
    # Tudo (stdout+stderr) vai pro log file, stdin /dev/null.
    log_fh = log_path.open("ab")
    devnull_fh = open(os.devnull, "rb")
    try:
        proc = subprocess.Popen(
            ["uv", "run", "python", "-m", runner_module, jira_issue_key],
            cwd=str(DEFAULT_REPO_ROOT),
            stdin=devnull_fh,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # equivalente a setsid
            close_fds=True,
        )
    finally:
        # Os handles ficam abertos no subprocess; o pai pode fechar.
        log_fh.close()
        devnull_fh.close()

    logger.info(
        "trigger_agent_run: pid=%s tier=%s issue=%s task=%s log=%s",
        proc.pid,
        tier.value,
        jira_issue_key,
        task.id,
        log_path,
    )

    return {
        "task_id": task.id,
        "jira_issue_key": jira_issue_key,
        "agent_id": agent.id,
        "tier": tier.value,
        "pid": proc.pid,
        "log_path": str(log_path),
    }
