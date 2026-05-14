"""Roda o Onboarding Analyst v1 contra um repositorio local.

Inspeciona estaticamente um repo (analyze_repo) e produz proposta de
manifesto + .dev-autonomo.yml + skill templates recomendados.

Uso:
    uv run python -m scripts.dev.run_onboarding_analyst /home/rubens/dev-autonomo-workspace/dev-autonomo

Diferencia-se dos run_*_task.py por nao operar sobre uma issue Jira —
o "task" e o onboarding em si.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from dev_autonomo.agent_runtime.toolset.repo_analyzer import AnalyzeRepoTool
from dev_autonomo.common.enums import AgentTier
from dev_autonomo.db.models import AgentInstance, Client, SkillTemplate, Squad
from scripts.dev._runner_lib import TaskSpec, run_task

AGENT_NAME = "Onboarding Analyst Plataforma"
SKILL_TEMPLATE_SLUG = "onboarding-analyst-v1"


async def _ensure_oa_agent(
    session, client: Client, squad: Squad
) -> AgentInstance:
    """Provisiona o AgentInstance Onboarding Analyst (idempotente)."""
    tpl = (
        await session.execute(
            select(SkillTemplate).where(
                SkillTemplate.slug == SKILL_TEMPLATE_SLUG,
                SkillTemplate.version == 1,
            )
        )
    ).scalar_one()

    print(f"  + AgentInstance '{AGENT_NAME}' nao encontrado, criando...")
    agent = AgentInstance(
        client_id=squad.client_id,
        squad_id=squad.id,
        skill_template_id=tpl.id,
        name=AGENT_NAME,
        domain_business=AgentTier.ONBOARDING_ANALYST,
    )
    session.add(agent)
    await session.flush()
    print(f"  + AgentInstance criado: {agent.name} ({agent.id})")
    return agent


def _main() -> None:
    if len(sys.argv) < 2:
        print(
            "Uso: python -m scripts.dev.run_onboarding_analyst <repo_path> [client_slug] [squad_slug]"
        )
        sys.exit(1)
    repo_path = Path(sys.argv[1]).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        print(f"erro: repo_path invalido: {repo_path}")
        sys.exit(1)

    client_slug = sys.argv[2] if len(sys.argv) > 2 else "dev-autonomo"
    squad_slug = sys.argv[3] if len(sys.argv) > 3 else "plataforma"

    issue_key = f"ONBOARD-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    spec = TaskSpec(
        agent_name=AGENT_NAME,
        client_slug=client_slug,
        squad_slug=squad_slug,
        needs_workspace=False,
        needs_indexed_knowledge=False,
        system_prompt_path=Path("prompts/onboarding/analyst.md"),
        ensure_agent=_ensure_oa_agent,
        max_turns=15,
        model="claude-sonnet-4-6",  # opus seria ideal mas sonnet barato pra smoke
        user_prompt_builder=lambda _issue: (
            f"Faca o onboarding analitico do repo localizado em:\n"
            f"  {repo_path}\n\n"
            f"Siga seu fluxo padrao: analyze_repo -> retrieve_knowledge -> "
            f"proposta completa via signal_complete."
        ),
        tools=[
            AnalyzeRepoTool(),
        ],
    )

    asyncio.run(run_task(spec, issue_key))


if __name__ == "__main__":
    _main()
