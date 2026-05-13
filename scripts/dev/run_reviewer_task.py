"""Demo end-to-end: Reviewer Agent revisa um PR aberto no obris-dev-squad-agent.

Conecta tudo: pega um PR aberto, instancia o agente Reviewer Plataforma,
e roda o fluxo de revisao completo:
  1. github_get_pr  → le o PR (titulo, body, diff, arquivos)
  2. retrieve_knowledge (conventions + playbook) → busca regras da squad
  3. Avalia: testes, lint, aderencia a padroes, escopo proporcional
  4. github_review_pr → APPROVE ou REQUEST_CHANGES + body PT-BR
  5. Se PR linkado a Jira (parsing do body/branch) → jira_add_comment (opcional)
  6. signal_complete

CRITERIOS DE ACEITACAO:
- Script roda sem erros contra um PR aberto.
- Reviewer posta review no PR (visivel no GitHub).
- Cost tracking grava ExternalApiCall com agent_instance_id do Reviewer.
- Sem merge automatico — review only.

DEPENDENCIAS: LEO-6 (tools reviewer.py) e LEO-7 (skill template reviewer)
              devem estar mergeados. O seed do Reviewer Plataforma deve ter
              sido executado (run via seed_platform_data.py ou este proprio
              script provisiona em modo --seed-only se necessario).

Uso:
    uv run python -m scripts.dev.run_reviewer_task <pr_number>

    # Exemplos:
    uv run python -m scripts.dev.run_reviewer_task 42
    uv run python -m scripts.dev.run_reviewer_task 42 --seed-only
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.enforcement import ManifestEnforcer
from dev_autonomo.agent_runtime.toolset.base import ToolRegistry
from dev_autonomo.agent_runtime.toolset.basic import (
    RetrieveKnowledgeTool,
    SignalCompleteTool,
)
from dev_autonomo.agent_runtime.toolset.reviewer import (
    GitHubGetPRTool,
    GitHubReviewPRTool,
)
from dev_autonomo.agent_runtime.worker import AgentRunner
from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.common.enums import AgentTier, AgentInstanceStatus
from dev_autonomo.db.models import (
    AgentInstance,
    Client,
    SkillTemplate,
    Squad,
)
from dev_autonomo.db.session import session_scope
from dev_autonomo.knowledge.qdrant_client import QdrantKnowledgeStore
from dev_autonomo.knowledge.retriever import KnowledgeRetriever
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# ---- Constantes do cliente dev-autonomo / squad plataforma ----
CLIENT_SLUG = "dev-autonomo"
SQUAD_SLUG = "plataforma"
AGENT_NAME = "Reviewer Plataforma"
SKILL_TEMPLATE_SLUG = "reviewer-plataforma-v1"
REPO_URL = "https://github.com/obris-dev/obris-dev-squad-agent"

# Ferramentas habilitadas para o Reviewer
REVIEWER_TOOLS = [
    "github_get_pr",
    "retrieve_knowledge",
    "github_review_pr",
    "signal_complete",
    # jira_add_comment e jira_get_issue ficam opcionais mas registrados
    # (o agente decidirá se o PR está linkado a uma issue)
]

# ---- System Prompt do Reviewer ----
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


async def _ensure_reviewer_skill_template(session) -> SkillTemplate:
    """Garante que o SkillTemplate 'reviewer-plataforma-v1' existe (idempotente)."""
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
        print(f"  + SkillTemplate '{SKILL_TEMPLATE_SLUG}' nao encontrado, criando...")
        tpl = SkillTemplate(
            client_id=None,  # SYSTEM-level, compartilhado
            slug=SKILL_TEMPLATE_SLUG,
            name="Reviewer Plataforma",
            description=(
                "Agente Reviewer da squad Plataforma. "
                "Revisa PRs com foco em qualidade, testes, convencoes e seguranca."
            ),
            version=1,
            tier=AgentTier.DEV,  # tier mais proximo para reviewers
            model_alias="claude-sonnet-4-6",
            stack_primary={"role": "reviewer"},
            stack_secondary=[],
            system_prompt_ref="prompts/reviewer/plataforma.md",
            tools_enabled=REVIEWER_TOOLS,
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
    else:
        print(f"  = SkillTemplate ja existe: {tpl.slug} ({tpl.id})")

    return tpl


async def _ensure_reviewer_agent(session, squad: Squad, tpl: SkillTemplate) -> AgentInstance:
    """Garante que o AgentInstance 'Reviewer Plataforma' existe na squad (idempotente)."""
    agent = (
        await session.execute(
            select(AgentInstance).where(
                AgentInstance.squad_id == squad.id,
                AgentInstance.name == AGENT_NAME,
            )
        )
    ).scalar_one_or_none()

    if agent is None:
        print(f"  + AgentInstance '{AGENT_NAME}' nao encontrado, criando...")
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
    else:
        print(f"  = AgentInstance ja existe: {agent.name} ({agent.id})")

    return agent


async def main(pr_number: int, seed_only: bool = False) -> None:
    print("=" * 70)
    print(f"DEMO END-TO-END: Reviewer Plataforma -> revisando PR #{pr_number}")
    print("=" * 70)

    async with session_scope() as session:
        # ---- 1. Resolve identidades ----
        print("\n[1/6] Resolvendo identidades (client / squad / agent)...")

        client = (
            await session.execute(
                select(Client).where(Client.slug == CLIENT_SLUG)
            )
        ).scalar_one_or_none()
        if client is None:
            print(f"ERRO: Client '{CLIENT_SLUG}' nao encontrado no banco.")
            print("Execute seed_platform_data.py primeiro.")
            return

        squad = (
            await session.execute(
                select(Squad).where(
                    Squad.client_id == client.id,
                    Squad.slug == SQUAD_SLUG,
                )
            )
        ).scalar_one_or_none()
        if squad is None:
            print(f"ERRO: Squad '{SQUAD_SLUG}' nao encontrada para client '{CLIENT_SLUG}'.")
            print("Execute seed_platform_data.py primeiro.")
            return

        print(f"  client : {client.slug} ({client.id})")
        print(f"  squad  : {squad.slug} ({squad.id})")

        # ---- 2. Garante SkillTemplate + AgentInstance do Reviewer ----
        print("\n[2/6] Garantindo SkillTemplate e AgentInstance do Reviewer...")
        tpl = await _ensure_reviewer_skill_template(session)
        agent = await _ensure_reviewer_agent(session, squad, tpl)
        await session.commit()

        if seed_only:
            print("\n--seed-only: encerrando apos provisionar identidades.")
            return

        # ---- 3. Monta contexto de execucao ----
        print("\n[3/6] Montando contexto de execucao...")
        voyage = VoyageEmbeddingClient(session=session)
        qdrant = QdrantKnowledgeStore()
        retriever = KnowledgeRetriever(session=session, voyage=voyage, qdrant=qdrant)
        enforcer = ManifestEnforcer(
            session=session, client_id=client.id, squad_id=squad.id
        )
        ctx = AgentRunContext(
            client_id=client.id,
            squad_id=squad.id,
            agent_instance_id=agent.id,  # cost tracking grava com agent_instance_id
            task_id=None,
            session=session,
            claude=ClaudeClient(session=session),
            voyage=voyage,
            qdrant=qdrant,
            retriever=retriever,
            enforcer=enforcer,
            workspace_root=None,      # Reviewer nao precisa de workspace local
            workspace_repo=REPO_URL,  # usado pelo github_get_pr / github_review_pr
        )
        print(f"  agent_instance_id para cost tracking: {agent.id}")

        # ---- 4. Registra tools do Reviewer ----
        print("\n[4/6] Registrando ferramentas do Reviewer...")
        registry = ToolRegistry()
        registry.register(GitHubGetPRTool())
        registry.register(GitHubReviewPRTool())
        registry.register(RetrieveKnowledgeTool())
        registry.register(SignalCompleteTool())
        print(f"  tools registradas: {list(registry.tools.keys())}")

        # ---- 5. Monta runner e dispara ----
        print("\n[5/6] Iniciando AgentRunner (Reviewer)...")
        runner = AgentRunner(
            ctx=ctx,
            registry=registry,
            model="claude-sonnet-4-6",
            max_turns=20,
            max_tokens_per_turn=8192,
        )

        user_prompt = (
            f"Revise o Pull Request #{pr_number} do repositorio {REPO_URL}.\n\n"
            "Siga o fluxo obrigatorio do system prompt:\n"
            f"1. github_get_pr(pr_number={pr_number}) para ler o PR\n"
            "2. retrieve_knowledge nas partitions conventions e playbook\n"
            "3. Avalie testes, lint, aderencia a padroes, escopo proporcional\n"
            "4. github_review_pr com decision APPROVE ou REQUEST_CHANGES + body PT-BR\n"
            "5. (Opcional) Se o body/branch mencionar Jira (ex: LEO-N), "
            "use jira_add_comment para notificar a issue\n"
            "6. signal_complete\n"
        )

        result = await runner.run(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            enabled_tools=REVIEWER_TOOLS,
        )

        # ---- 6. Imprime resultado ----
        print("\n" + "=" * 70)
        print("RESULTADO DA REVISAO")
        print("=" * 70)
        print(f"completed:       {result.completed}")
        print(f"turnos:          {result.turn_count}")
        print(f"tool calls:      {len(result.tool_calls)}")
        print(f"  sequencia:     {' -> '.join(result.tool_calls)}")
        print(f"custo total:     US$ {result.total_cost_usd:.4f}")
        print(f"agent_id:        {agent.id}  (cost tracking)")

        if result.error:
            print(f"\nERRO: {result.error}")

        if result.completion_summary:
            print("\nSUMARIO DO REVIEWER:")
            print(result.completion_summary)
            if result.completion_deliverables:
                print("\nDELIVERABLES:")
                for d in result.completion_deliverables:
                    print(f"  - {d}")
        elif result.final_text:
            print("\nRESPOSTA FINAL:")
            print(result.final_text[:2000])

        await qdrant.close()


def _usage_and_exit() -> None:
    print("Uso: uv run python -m scripts.dev.run_reviewer_task <pr_number> [--seed-only]")
    print("\nExemplos:")
    print("  uv run python -m scripts.dev.run_reviewer_task 42")
    print("  uv run python -m scripts.dev.run_reviewer_task 42 --seed-only")
    sys.exit(1)


def main_cli() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        _usage_and_exit()

    try:
        pr_number = int(args[0])
    except ValueError:
        print(f"ERRO: pr_number deve ser um inteiro, recebido: '{args[0]}'")
        _usage_and_exit()

    seed_only = "--seed-only" in args
    asyncio.run(main(pr_number=pr_number, seed_only=seed_only))


if __name__ == "__main__":
    main_cli()
