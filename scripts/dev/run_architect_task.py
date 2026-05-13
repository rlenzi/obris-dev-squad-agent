"""Roda o Architect Plataforma em uma issue Jira.

Decompoe a demanda em sub-tarefas executaveis usando o agente Architect
(tier ARCHITECT, skill template architect-generic-v1).

Uso:
    uv run python -m scripts.dev.run_architect_task LEO-22

O agente le a issue, analisa o contexto do codebase e cria sub-tarefas
no Jira via jira_create_subtask.

NOTAS:
- workspace_root e omitido (Architect nao mexe em filesystem).
- AgentInstance e provisionada de forma idempotente (_ensure_architect_agent).
- Cost tracking grava ExternalApiCall com o agent_instance_id do Architect.
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
from dev_autonomo.agent_runtime.toolset.jira import (
    JiraAddCommentTool,
    JiraCreateSubtaskTool,
    JiraGetIssueTool,
    JiraUpdateStatusTool,
)
from dev_autonomo.agent_runtime.worker import AgentRunner
from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.common.enums import AgentTier
from dev_autonomo.db.models import AgentInstance, Client, SkillTemplate, Squad
from dev_autonomo.db.session import session_scope
from dev_autonomo.knowledge.qdrant_client import QdrantKnowledgeStore
from dev_autonomo.knowledge.retriever import KnowledgeRetriever
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
# Silencia ruido SQL
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# ---- Constantes do tenant / squad / agente ----
CLIENT_SLUG = "dev-autonomo"
SQUAD_SLUG = "plataforma"
AGENT_NAME = "Architect Plataforma"
SKILL_TEMPLATE_SLUG = "architect-generic-v1"


async def _ensure_architect_agent(
    session,
    squad: Squad,
    tpl: SkillTemplate,
) -> AgentInstance:
    """Garante que o AgentInstance do Architect existe (idempotente).

    Se ja existir, retorna o existente sem alterar nada.
    Se nao existir, cria com tier=ARCHITECT e skill template architect-generic-v1.
    """
    existing = (
        await session.execute(
            select(AgentInstance).where(
                AgentInstance.squad_id == squad.id,
                AgentInstance.name == AGENT_NAME,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        print(f"= AgentInstance ja existe: {AGENT_NAME} ({existing.id})")
        return existing

    agent = AgentInstance(
        client_id=squad.client_id,
        squad_id=squad.id,
        skill_template_id=tpl.id,
        name=AGENT_NAME,
        domain_business=AgentTier.ARCHITECT,
    )
    session.add(agent)
    await session.flush()
    print(f"+ AgentInstance criado: {AGENT_NAME} ({agent.id})")
    return agent


async def main(issue_key: str) -> None:
    print("=" * 70)
    print(f"Architect Plataforma -> decomposicao de {issue_key}")
    print("=" * 70)

    async with session_scope() as session:
        # 1. Resolve client / squad
        client = (
            await session.execute(select(Client).where(Client.slug == CLIENT_SLUG))
        ).scalar_one()

        squad = (
            await session.execute(
                select(Squad).where(
                    Squad.client_id == client.id, Squad.slug == SQUAD_SLUG
                )
            )
        ).scalar_one()

        # 2. Resolve skill template architect-generic-v1
        tpl = (
            await session.execute(
                select(SkillTemplate).where(
                    SkillTemplate.slug == SKILL_TEMPLATE_SLUG,
                    SkillTemplate.version == 1,
                )
            )
        ).scalar_one()

        # 3. Garante AgentInstance do Architect (idempotente)
        agent = await _ensure_architect_agent(session, squad, tpl)

        # 4. Le system_prompt de prompts/architect/generic.md
        prompt_path = Path("prompts/architect/generic.md")
        system_prompt = prompt_path.read_text(encoding="utf-8")

        # 5. Monta AgentRunContext
        #    workspace_root omitido — Architect nao mexe em filesystem
        voyage = VoyageEmbeddingClient(session=session)
        qdrant = QdrantKnowledgeStore()
        retriever = KnowledgeRetriever(session=session, voyage=voyage, qdrant=qdrant)
        enforcer = ManifestEnforcer(
            session=session, client_id=client.id, squad_id=squad.id
        )
        ctx = AgentRunContext(
            client_id=client.id,
            squad_id=squad.id,
            agent_instance_id=agent.id,
            task_id=None,
            session=session,
            claude=ClaudeClient(session=session),
            voyage=voyage,
            qdrant=qdrant,
            retriever=retriever,
            enforcer=enforcer,
            workspace_root=None,
            workspace_repo="https://github.com/rlenzi/obris-dev-squad-agent",
        )

        # 6. Registra tools
        registry = ToolRegistry()
        registry.register(RetrieveKnowledgeTool())
        registry.register(JiraGetIssueTool())
        registry.register(JiraCreateSubtaskTool())
        registry.register(JiraAddCommentTool())
        registry.register(JiraUpdateStatusTool())
        registry.register(SignalCompleteTool())

        enabled_tools = [
            "retrieve_knowledge",
            "jira_get_issue",
            "jira_create_subtask",
            "jira_add_comment",
            "jira_update_status",
            "signal_complete",
        ]

        # 7. Monta user_prompt
        user_prompt = (
            f"Decomponha a demanda Jira {issue_key} em sub-tarefas executaveis "
            "seguindo seu fluxo padrao."
        )

        # 8. Executa via AgentRunner
        runner = AgentRunner(
            ctx=ctx,
            registry=registry,
            model="claude-sonnet-4-6",
            max_turns=20,
            max_tokens_per_turn=8192,
        )

        print(f"\nIniciando Architect para {issue_key}...")
        print("=" * 70)

        result = await runner.run(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            enabled_tools=enabled_tools,
        )

        await qdrant.close()

        # 9. Exibe resultado
        print("\n" + "=" * 70)
        print("RESULTADO")
        print("=" * 70)
        print(f"completed:       {result.completed}")
        print(f"turnos:          {result.turn_count}")
        print(f"tool calls:      {len(result.tool_calls)}")
        print(f"  sequencia:     {' -> '.join(result.tool_calls)}")
        print(f"custo total:     US$ {result.total_cost_usd:.4f}")
        if result.error:
            print(f"erro:            {result.error}")
        print()
        if result.completion_summary:
            print("SUMARIO DO AGENTE:")
            print(result.completion_summary)
            if result.completion_deliverables:
                print("\nDELIVERABLES:")
                for d in result.completion_deliverables:
                    print(f"  - {d}")
        elif result.final_text:
            print("RESPOSTA FINAL:")
            print(result.final_text[:2000])


def _parse_issue_key() -> str:
    """Extrai issue_key do argv (ex: 'LEO-22')."""
    if len(sys.argv) < 2:
        print("Uso: uv run python -m scripts.dev.run_architect_task <ISSUE_KEY>")
        print("Ex:  uv run python -m scripts.dev.run_architect_task LEO-22")
        sys.exit(1)
    return sys.argv[1].strip().upper()


if __name__ == "__main__":
    issue_key = _parse_issue_key()
    asyncio.run(main(issue_key))
