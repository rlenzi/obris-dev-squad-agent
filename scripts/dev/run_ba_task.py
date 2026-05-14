"""Roda o BA Plataforma em uma issue Jira.

Refina uma demanda vaga em história de usuário com critérios de aceitação
explícitos, usando o agente BA (tier BA, skill template ba-generic-v1).

Uso:
    uv run python -m scripts.dev.run_ba_task LEO-XX

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
)
from dev_autonomo.common.enums import AgentTier
from dev_autonomo.db.models import AgentInstance, Client, SkillTemplate, Squad
from scripts.dev._runner_lib import TaskSpec, parse_issue_key, run_task

AGENT_NAME = "BA Plataforma"
SKILL_TEMPLATE_SLUG = "ba-generic-v1"


async def _ensure_ba_agent(
    session, client: Client, squad: Squad
) -> AgentInstance:
    """Provisiona o AgentInstance BA Plataforma (idempotente)."""
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
        domain_business=AgentTier.BA,
    )
    session.add(agent)
    await session.flush()
    print(f"  + AgentInstance criado: {agent.name} ({agent.id})")
    return agent


SPEC = TaskSpec(
    agent_name=AGENT_NAME,
    needs_workspace=False,
    needs_indexed_knowledge=False,
    system_prompt_path=Path("prompts/ba/generic.md"),
    ensure_agent=_ensure_ba_agent,
    max_turns=15,
    user_prompt_builder=lambda issue: (
        f"Refine a demanda Jira {issue} seguindo seu fluxo padrao: leia o "
        f"contexto, identifique ambiguidade, e produza um comentario com "
        f"Como/Quero/Para-que/Criterios de Aceitacao/Fora-de-escopo/Duvidas."
    ),
    tools=[
        JiraGetIssueTool(),
        JiraCreateSubtaskTool(),
        JiraAddCommentTool(),
    ],
)


if __name__ == "__main__":
    asyncio.run(run_task(SPEC, parse_issue_key("run_ba_task")))
