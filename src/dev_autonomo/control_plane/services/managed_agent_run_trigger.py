"""Trigger de agent run via Managed Agents (substitui subprocess do worker velho).

Diferencas vs ``agent_run_trigger.py`` legado:
- Sem subprocess — chama ``managed_runner.run_managed_task`` diretamente.
- Async em background via ``asyncio.create_task`` (HTTP request retorna
  imediatamente; runner roda em paralelo ate session.status_idle).
- Persiste ``anthropic_session_id`` em ``tasks`` desde a criacao da
  session (queryable pelo painel pra deep-link).
- Monta ``resources`` automaticamente:
  - Se client.jira_secrets_file_id setado: file resource jira.env.
  - Se squad tem repo configurado (T10+): github_repository resource.

Feature flag: ``DEV_AUTONOMO_USE_MANAGED`` controla wrapper em
``agent_run_trigger.trigger_agent_run_smart``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.agent_runtime.managed_runner import (
    ManagedTaskSpec,
    run_managed_task,
)
from dev_autonomo.common.enums import AgentTier
from dev_autonomo.db.models import AgentInstance, Client, Squad, Task

logger = logging.getLogger(__name__)

PROMPTS_BASE = Path(
    "/home/rubens/dev-autonomo-workspace/dev-autonomo/prompts"
)

# Mapeamento tier -> path do prompt managed.md (relativo a PROMPTS_BASE).
TIER_PROMPT: dict[AgentTier, str] = {
    AgentTier.BA: "ba/managed.md",
    AgentTier.ARCHITECT: "architect/managed.md",
    AgentTier.DEV: "dev/managed.md",
    AgentTier.REVIEWER: "reviewer/managed.md",       # criado em T10
    AgentTier.ONBOARDING_ANALYST: "onboarding/managed.md",  # criado em T10
}


class ManagedTriggerError(Exception):
    """Erro funcional do trigger managed."""


def _build_user_prompt_for_tier(
    tier: AgentTier,
    issue_url: str | None,
    github_repo_url: str | None,
) -> callable:
    """Constroi callable user_prompt_builder(issue_key) -> str por tier.

    O builder eh chamado pelo runner com a issue_key. Cada tier tem
    contexto inicial diferente.
    """

    def build(issue_key: str) -> str:
        lines = [f"Issue Jira a tratar: **{issue_key}**"]
        if issue_url:
            lines.append(f"URL: {issue_url}")
        lines.append("")

        # Credenciais agora chegam via file resource em /mnt/secrets/jira.env
        # (caso o cliente tenha sincronizado). Agente faz `source` no
        # primeiro bash. Se file resource nao foi montado (cliente sem
        # token sincronizado), agente vai falhar no primeiro curl — esperado.
        lines.append(
            "Credenciais Jira: `source /mnt/secrets/jira.env` no primeiro "
            "bash exporta JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN."
        )

        if tier in (AgentTier.DEV, AgentTier.REVIEWER, AgentTier.ARCHITECT):
            if github_repo_url:
                lines.append(
                    f"Repositório alvo: **{github_repo_url}** ja montado em "
                    f"`/mnt/repo` via github_repository resource (commit "
                    f"pushable, token GitHub embedded). Nao clone manualmente."
                )
            else:
                lines.append(
                    "Repositório alvo nao configurado nesta squad — "
                    "Reportar e encerrar."
                )

        if tier == AgentTier.BA:
            lines.append("Siga o fluxo obrigatorio do system prompt (§5).")
        elif tier == AgentTier.ARCHITECT:
            lines.append(
                "Siga o fluxo obrigatorio do system prompt. Decomponha em "
                "sub-tarefas e delegue aos sub-agents (Dev BE/FE) do seu "
                "roster quando apropriado."
            )
        elif tier == AgentTier.DEV:
            lines.append("Siga o fluxo obrigatorio do system prompt (§3).")
        elif tier == AgentTier.REVIEWER:
            lines.append("Faca review do PR aberto associado a esta issue.")

        return "\n".join(lines)

    return build


async def trigger_managed_agent_run(
    *,
    session: AsyncSession,
    client: Client,
    agent_id: UUID,
    jira_issue_key: str,
    background: bool = True,
) -> dict[str, object]:
    """Dispara agente via managed_runner. Retorna metadados imediatamente.

    ``background=True`` (default) cria asyncio.Task que roda em paralelo.
    ``background=False`` aguarda completar (uso pra smoke/testes).
    """
    # 1. Resolve agent + squad
    agent = (
        await session.execute(
            select(AgentInstance).where(
                AgentInstance.id == agent_id,
                AgentInstance.client_id == client.id,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise ManagedTriggerError(f"agente {agent_id} nao encontrado no cliente.")

    squad = (
        await session.execute(select(Squad).where(Squad.id == agent.squad_id))
    ).scalar_one_or_none()
    if squad is None:
        raise ManagedTriggerError(f"squad {agent.squad_id} nao encontrada.")

    # 2. Resolve tier + prompt
    # Note: tier vem do skill_template, nao do agent_instance.
    # AgentInstance.domain_business eh string de dominio; tier vem via tpl.
    from dev_autonomo.db.models import SkillTemplate
    tpl = (
        await session.execute(
            select(SkillTemplate).where(SkillTemplate.id == agent.skill_template_id)
        )
    ).scalar_one()
    tier = tpl.tier

    prompt_path = PROMPTS_BASE / TIER_PROMPT.get(tier, "")
    if not prompt_path.exists():
        raise ManagedTriggerError(
            f"prompt managed.md para tier {tier.value} ausente em {prompt_path}. "
            f"Crie em PRs futuras (T10 cobre OA + Reviewer)."
        )

    # 3. Cria/recupera Task local
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
    task_id = task.id

    # 4. Monta resources
    resources: list[dict] = []
    if client.jira_secrets_file_id:
        resources.append({
            "type": "file",
            "file_id": client.jira_secrets_file_id,
            "mount_path": "/mnt/secrets/jira.env",
        })

    # Resolve repo URL e auth a partir da squad (Manifest tem repos).
    github_repo_url: str | None = None
    github_token: str | None = None
    if tier in (AgentTier.DEV, AgentTier.REVIEWER, AgentTier.ARCHITECT):
        github_repo_url, github_token = await _resolve_github_resource_for_squad(
            session, client, squad
        )
        if github_repo_url and github_token:
            resources.append({
                "type": "github_repository",
                "url": github_repo_url,
                "authorization_token": github_token,
                "checkout": {"type": "branch", "name": "main"},
                "mount_path": "/mnt/repo",
            })

    issue_url = (
        f"{client.jira_workspace_url}/browse/{jira_issue_key}"
        if client.jira_workspace_url else None
    )

    spec = ManagedTaskSpec(
        agent_name=agent.name,
        system_prompt_path=prompt_path,
        client_slug=client.slug,
        squad_slug=squad.slug,
        model=tpl.model_alias,
        resources=resources,
        user_prompt_builder=_build_user_prompt_for_tier(
            tier, issue_url, github_repo_url,
        ),
    )

    logger.info(
        "trigger_managed: tier=%s task=%s issue=%s resources=%d background=%s",
        tier.value, task_id, jira_issue_key, len(resources), background,
    )

    if background:
        # Dispara em background — request HTTP retorna logo.
        asyncio.create_task(_run_in_background(spec, jira_issue_key, task_id))
    else:
        await run_managed_task(spec, jira_issue_key)

    return {
        "task_id": task_id,
        "jira_issue_key": jira_issue_key,
        "agent_id": agent.id,
        "tier": tier.value,
        "background": background,
        "resources_count": len(resources),
    }


async def _run_in_background(
    spec: ManagedTaskSpec, issue_key: str, task_id: UUID,
) -> None:
    """Wrapper que loga falhas em background sem propagar."""
    try:
        result = await run_managed_task(spec, issue_key)
        logger.info(
            "managed_run done task=%s issue=%s completed=%s session=%s cost=%s",
            task_id, issue_key, result.completed, result.session_id, result.cost_usd,
        )
    except Exception:
        logger.exception(
            "managed_run falhou em background task=%s issue=%s",
            task_id, issue_key,
        )


async def _resolve_github_resource_for_squad(
    session: AsyncSession, client: Client, squad: Squad,
) -> tuple[str | None, str | None]:
    """Retorna (repo_url, github_token) para a squad.

    Token vem de EncryptedSecret kind=github_token do client (V1, sem
    rotacao por repo).
    URL vem do manifest atual da squad (T10+ vai povoar). Por ora,
    tenta extrair de squad.domain ou retorna None.
    """
    # TODO(T10): puxar URL canonico do manifest atual da squad. Por
    # hora, retorna None pra clientes sem squad config completa.
    repo_url: str | None = None

    # Hardcode pra dev-autonomo / Plataforma como dogfooding:
    if client.slug == "dev-autonomo" and squad.slug == "plataforma":
        repo_url = "https://github.com/rlenzi/obris-dev-squad-agent"

    if not repo_url:
        return None, None

    # Resolve GitHub token via EncryptedSecret
    from dev_autonomo.common.encryption import SecretEncryptor
    from dev_autonomo.common.enums import SecretKind
    from dev_autonomo.db.models import EncryptedSecret

    cred = (
        await session.execute(
            select(EncryptedSecret).where(
                EncryptedSecret.client_id == client.id,
                EncryptedSecret.kind == SecretKind.GITHUB_TOKEN,
            )
        )
    ).scalar_one_or_none()
    if cred is None:
        return repo_url, None

    return repo_url, SecretEncryptor().decrypt(cred.encrypted_value)
