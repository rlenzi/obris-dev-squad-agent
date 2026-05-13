"""Roda o Architect Plataforma em uma issue Jira.

Decompõe a demanda em sub-tarefas executáveis usando o agente Architect
(tier ARCHITECT, skill template architect-generic-v1).

Uso:
    uv run python -m scripts.dev.run_architect_task LEO-22

Implementação compacta usando ``scripts.dev._runner_lib.run_task``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from dev_autonomo.agent_runtime.toolset.jira import (
    JiraAddCommentTool,
    JiraCreateSubtaskTool,
    JiraGetIssueTool,
    JiraUpdateStatusTool,
)
from dev_autonomo.common.enums import AgentTier
from dev_autonomo.db.models import AgentInstance, Client, SkillTemplate, Squad
from scripts.dev._runner_lib import TaskSpec, parse_issue_key, run_task

AGENT_NAME = "Architect Plataforma"
SKILL_TEMPLATE_SLUG = "architect-generic-v1"


async def _ensure_architect_agent(
    session, client: Client, squad: Squad
) -> AgentInstance:
    """Provisiona o AgentInstance Architect Plataforma (idempotente)."""
    tpl = (
        await session.execute(
            select(SkillTemplate).where(
                SkillTemplate.slug == SKILL_TEMPLATE_SLUG,
                SkillTemplate.version == 1,
            )
        )
    ).scalar_one()

    print(f"  + AgentInstance '{AGENT_NAME}' não encontrado, criando...")
    agent = AgentInstance(
        client_id=squad.client_id,
        squad_id=squad.id,
        skill_template_id=tpl.id,
        name=AGENT_NAME,
        domain_business=AgentTier.ARCHITECT,
    )
    session.add(agent)
    await session.flush()
    print(f"  + AgentInstance criado: {agent.name} ({agent.id})")
    return agent


SPEC = TaskSpec(
    agent_name=AGENT_NAME,
    needs_workspace=False,
    needs_indexed_knowledge=False,
    system_prompt_path=Path("prompts/architect/generic.md"),
    ensure_agent=_ensure_architect_agent,
    max_turns=20,
    user_prompt_builder=lambda issue: (
        f"Decomponha a demanda Jira {issue} em sub-tarefas executaveis "
        f"seguindo seu fluxo padrao."
    ),
    tools=[
        JiraGetIssueTool(),
        JiraCreateSubtaskTool(),
        JiraAddCommentTool(),
        JiraUpdateStatusTool(),
    ],
)


if __name__ == "__main__":
    asyncio.run(run_task(SPEC, parse_issue_key("run_architect_task")))
