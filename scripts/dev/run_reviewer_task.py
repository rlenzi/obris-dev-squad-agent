"""Demo end-to-end: Reviewer Agent revisa um PR aberto.

Uso:
    uv run python -m scripts.dev.run_reviewer_task 14

Implementação compacta usando ``scripts.dev._runner_lib.run_task`` com
``ensure_agent`` que provisiona o AgentInstance Reviewer Plataforma + seu
SkillTemplate caso ainda não existam.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from dev_autonomo.agent_runtime.toolset.github import (
    GitHubGetPRTool,
    GitHubReviewPRTool,
)
from dev_autonomo.agent_runtime.toolset.jira import (
    JiraAddCommentTool,
    JiraGetIssueTool,
    JiraUpdateStatusTool,
)
from dev_autonomo.common.enums import AgentInstanceStatus, AgentTier
from dev_autonomo.db.models import AgentInstance, Client, SkillTemplate, Squad

from scripts.dev._runner_lib import TaskSpec, parse_issue_key, run_task


AGENT_NAME = "Reviewer Plataforma"
SKILL_TEMPLATE_SLUG = "reviewer-generic-v1"


SYSTEM_PROMPT = """\
Voce e um Reviewer senior da squad Plataforma do projeto dev-autonomo.
Sua funcao e revisar Pull Requests com rigor tecnico e clareza, escrevendo
sempre em portugues do Brasil.

FLUXO OBRIGATORIO:
1. github_get_pr: leia o PR (titulo, body, diff, arquivos alterados).
2. retrieve_knowledge (partition=conventions): busque as convencoes de codigo da squad.
3. retrieve_knowledge (partition=playbook): busque boas praticas e licoes aprendidas.
4. Avalie criteriosamente:
   - Ha testes cobrindo as mudancas? (pytest, cobertura minima)
   - Lint e type hints ok? (ruff, mypy)
   - O codigo segue os padroes e convencoes da squad?
   - O escopo e proporcional? (PR gigante sem justificativa e sinal de alerta)
   - Seguranca: credenciais expostas, injecao de dependencia correta?
   - Mensagens de commit no padrao convencional ('feat:', 'fix:', 'docs:', etc.)?
5. github_review_pr: submeta o review com:
   - decision: APPROVE (se tudo ok) ou REQUEST_CHANGES (se precisar ajustes)
   - body: resumo da revisao em PT-BR (min. 2 paragrafos), referenciando
     arquivos/linhas especificos quando relevante.
6. (Opcional) Se o body ou branch do PR mencionar uma issue Jira (ex: LEO-42),
   use jira_add_comment para postar o resultado da revisao na issue.
7. signal_complete: sinalize o fim com summary e deliverables.

REGRAS:
- Nunca faca merge — review only.
- Body do review sempre em PT-BR.
- Seja especifico: cite arquivos e linhas, nao use linguagem vaga.
- Prefira REQUEST_CHANGES se houver duvida; seguranca em primeiro lugar.
"""


REVIEWER_TOOLS_ENABLED = [
    "github_get_pr",
    "retrieve_knowledge",
    "github_review_pr",
    "signal_complete",
    "jira_get_issue",
    "jira_update_status",
    "jira_add_comment",
]


async def _ensure_reviewer_agent(
    session, client: Client, squad: Squad
) -> AgentInstance:
    """Provisiona o SkillTemplate (se necessário) e o AgentInstance Reviewer."""
    tpl = (
        await session.execute(
            select(SkillTemplate).where(
                SkillTemplate.client_id.is_(None),
                SkillTemplate.slug == SKILL_TEMPLATE_SLUG,
                SkillTemplate.version == 1,
            )
        )
    ).scalar_one_or_none()

    if tpl is None:
        print(f"  + SkillTemplate '{SKILL_TEMPLATE_SLUG}' não encontrado, criando...")
        tpl = SkillTemplate(
            client_id=None,
            slug=SKILL_TEMPLATE_SLUG,
            name="Reviewer Plataforma",
            description=(
                "Agente Reviewer da squad Plataforma. "
                "Revisa PRs com foco em qualidade, testes, convenções e segurança."
            ),
            version=1,
            tier=AgentTier.REVIEWER,
            model_alias="claude-sonnet-4-6",
            stack_primary={"role": "reviewer"},
            stack_secondary=[],
            system_prompt_ref="prompts/reviewer/generic.md",
            tools_enabled=REVIEWER_TOOLS_ENABLED,
            knowledge_partitions=[
                "conventions:{squad}",
                "playbook:{squad}",
                "code:{squad}",
            ],
            active=True,
        )
        session.add(tpl)
        await session.flush()
        print(f"  + SkillTemplate criado: {tpl.slug} ({tpl.id})")

    print(f"  + AgentInstance '{AGENT_NAME}' não encontrado, criando...")
    agent = AgentInstance(
        client_id=squad.client_id,
        squad_id=squad.id,
        skill_template_id=tpl.id,
        name=AGENT_NAME,
        domain_business="code-review",
        status=AgentInstanceStatus.IDLE,
        config_overrides={},
    )
    session.add(agent)
    await session.flush()
    print(f"  + AgentInstance criado: {agent.name} ({agent.id})")
    return agent


SPEC = TaskSpec(
    agent_name=AGENT_NAME,
    needs_workspace=False,
    needs_indexed_knowledge=False,
    system_prompt=SYSTEM_PROMPT,
    ensure_agent=_ensure_reviewer_agent,
    user_prompt_builder=lambda pr_num: (
        f"Revise o Pull Request #{pr_num} do repositório "
        f"https://github.com/rlenzi/obris-dev-squad-agent.\n\n"
        f"Siga o fluxo obrigatório do system prompt:\n"
        f"1. github_get_pr(pr_number={pr_num}) para ler o PR\n"
        f"2. retrieve_knowledge nas partitions conventions e playbook\n"
        f"3. Avalie testes, lint, aderência a padrões, escopo\n"
        f"4. github_review_pr com decision APPROVE ou REQUEST_CHANGES + body PT-BR\n"
        f"5. (Opcional) jira_add_comment se o PR menciona issue Jira\n"
        f"6. signal_complete"
    ),
    tools=[
        GitHubGetPRTool(),
        GitHubReviewPRTool(),
        JiraGetIssueTool(),
        JiraUpdateStatusTool(),
        JiraAddCommentTool(),
    ],
)


def parse_pr_number() -> str:
    """Espera o número do PR como argv[1] (sem prefixo #)."""
    import sys
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.dev.run_reviewer_task <PR_NUMBER>")
        sys.exit(1)
    return sys.argv[1].strip().lstrip("#")


if __name__ == "__main__":
    asyncio.run(run_task(SPEC, parse_pr_number()))
