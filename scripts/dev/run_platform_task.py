"""Demo end-to-end completo: agente recebe issue do Jira, executa, abre PR,
fecha o ciclo de volta no Jira.

Uso:
    uv run python -m scripts.dev.run_platform_task LEO-1
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.enforcement import ManifestEnforcer
from dev_autonomo.agent_runtime.toolset.base import ToolRegistry
from dev_autonomo.agent_runtime.toolset.basic import (
    ReadFileTool,
    RetrieveKnowledgeTool,
    SignalCompleteTool,
)
from dev_autonomo.agent_runtime.toolset.files import (
    CreateFileTool,
    EditFileTool,
)
from dev_autonomo.agent_runtime.toolset.git import (
    GitCommitTool,
    GitDiffTool,
    GitStatusTool,
)
from dev_autonomo.agent_runtime.toolset.github import (
    GitHubCreatePRTool,
    GitPushTool,
)
from dev_autonomo.agent_runtime.toolset.jira import (
    JiraAddCommentTool,
    JiraGetIssueTool,
    JiraUpdateStatusTool,
)
from dev_autonomo.agent_runtime.worker import AgentRunner
from dev_autonomo.agent_runtime.worktree import GitWorktreeManager
from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.common.credentials_store import get_secret
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.db.models import AgentInstance, Client, Squad
from dev_autonomo.db.session import session_scope
from dev_autonomo.knowledge.indexer import CodeIndexer
from dev_autonomo.knowledge.qdrant_client import KnowledgePartition, QdrantKnowledgeStore
from dev_autonomo.knowledge.retriever import KnowledgeRetriever
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("voyage").setLevel(logging.WARNING)

REPO_URL = "https://github.com/rlenzi/obris-dev-squad-agent"
REPO_LOCAL = Path("/home/rubens/dev-autonomo-workspace/dev-autonomo")
WORKTREE_CACHE = Path("/home/rubens/dev-autonomo-workspace/worktree-cache")

SYSTEM_PROMPT = """\
Voce e um Dev Backend Python+FastAPI senior na squad Plataforma do projeto
dev-autonomo. Voce esta trabalhando no repo obris-dev-squad-agent.

FLUXO PADRAO (siga rigorosamente):
1. jira_get_issue para ler o objetivo, descricao completa, criterios.
2. jira_update_status para "Em andamento" (sinalizando inicio do trabalho).
3. jira_add_comment com mensagem curta tipo "Iniciei trabalho nesta tarefa.
   Vou investigar o repo e propor mudancas via PR."
4. Investigue o codigo com retrieve_knowledge + read_file conforme necessario.
5. Implemente a mudanca usando edit_file / create_file. Cada chamada passa
   pelo enforce do manifest.
6. git_status e git_diff pra revisar antes de commit.
7. git_commit (mensagem padrao: "tipo: descricao curta", ex: "docs: add contributing").
8. git_push (a branch ja foi criada pelo runtime).
9. github_create_pr (draft=true; titulo curto; body com "Closes LEO-N").
10. jira_add_comment com link do PR (URL completa).
11. signal_complete com summary + URL do PR.

NAO mude status para "Concluído" automaticamente — humano revisa o PR
primeiro.

REGRAS DE QUALIDADE:
- Linguagem do CONTEUDO: portugues do Brasil (a tarefa pede PT-BR).
- Linguagem de COMMIT e PR title: ingles ("docs:", "feat:", "fix:", ...).
- Sem especular. Investigue antes de escrever.
- Use no max 30 turnos.
"""


async def ensure_indexed(squad_id, client_id):
    store = QdrantKnowledgeStore()
    name = store.collection_name(KnowledgePartition.CODE, squad_id)
    try:
        if await store._client.collection_exists(name):
            count = await store.count(KnowledgePartition.CODE, squad_id)
            if count > 0:
                print(f"  Knowledge hub: {count} chunks ja indexados.")
                await store.close()
                return
    except Exception:
        pass

    print(f"  Indexando {REPO_LOCAL} ...")
    voyage = VoyageEmbeddingClient()
    indexer = CodeIndexer(voyage=voyage)
    result = await indexer.index_repo(
        client_id=client_id,
        squad_id=squad_id,
        repo_path=REPO_LOCAL,
        repo_label=REPO_URL + ".git",
    )
    print(
        f"  Indexado: {result.chunks_created} chunks, "
        f"US$ {result.embedding_cost_usd:.4f}, {result.duration_seconds:.1f}s"
    )
    await store.close()


async def main():
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.dev.run_platform_task <ISSUE-KEY>")
        sys.exit(1)
    issue_key = sys.argv[1].strip()

    print("=" * 70)
    print(f"DEMO END-TO-END · Squad Plataforma · Task {issue_key}")
    print("=" * 70)

    async with session_scope() as session:
        client = (
            await session.execute(select(Client).where(Client.slug == "dev-autonomo"))
        ).scalar_one()
        squad = (
            await session.execute(
                select(Squad).where(
                    Squad.client_id == client.id, Squad.slug == "plataforma"
                )
            )
        ).scalar_one()
        agent = (
            await session.execute(
                select(AgentInstance).where(
                    AgentInstance.squad_id == squad.id,
                    AgentInstance.name == "Dev Backend Plataforma",
                )
            )
        ).scalar_one()

        print(f"\nCliente:  {client.name} ({client.slug})")
        print(f"Squad:    {squad.name}")
        print(f"Agente:   {agent.name}")
        print(f"Issue:    {issue_key}")

        token = await get_secret(
            session, client_id=client.id, kind=SecretKind.GITHUB_TOKEN
        )
        await session.commit()

        print("\n-- Knowledge Hub --")
        await ensure_indexed(squad.id, client.id)

        print("\n-- Worktree --")
        mgr = GitWorktreeManager(cache_root=WORKTREE_CACHE)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug_part = issue_key.lower().replace(" ", "-")
        branch = f"agents/dev-backend/{slug_part}-{timestamp}"
        task_handle = f"task-{slug_part}-{timestamp}"
        wt = await mgr.checkout_for_task(
            client_id=client.id,
            repo_url=REPO_URL,
            task_handle=task_handle,
            new_branch=branch,
            github_token=token,
        )
        print(f"  branch:    {wt.branch}")

        voyage = VoyageEmbeddingClient(session=session)
        qdrant = QdrantKnowledgeStore()
        retriever = KnowledgeRetriever(session=session, voyage=voyage, qdrant=qdrant)
        enforcer = ManifestEnforcer(
            session=session,
            client_id=client.id,
            squad_id=squad.id,
            agent_instance_id=agent.id,
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
            workspace_root=wt.path,
            workspace_repo=REPO_URL,
        )

        registry = ToolRegistry()
        for tool in (
            RetrieveKnowledgeTool(),
            ReadFileTool(),
            EditFileTool(),
            CreateFileTool(),
            GitStatusTool(),
            GitDiffTool(),
            GitCommitTool(),
            GitPushTool(),
            GitHubCreatePRTool(),
            JiraGetIssueTool(),
            JiraUpdateStatusTool(),
            JiraAddCommentTool(),
            SignalCompleteTool(),
        ):
            registry.register(tool)

        enabled = [t.name for t in registry.tools.values()]

        runner = AgentRunner(
            ctx=ctx,
            registry=registry,
            model="claude-sonnet-4-6",
            max_turns=30,
            max_tokens_per_turn=4096,
        )

        user_prompt = (
            f"Sua task esta no Jira: {issue_key}. "
            f"Siga o fluxo padrao do system prompt: get_issue -> update_status "
            f"'Em andamento' -> add_comment 'iniciei' -> investigar codigo -> "
            f"implementar -> commit -> push -> create_pr -> add_comment com PR -> "
            f"signal_complete."
        )

        print("\n-- Agent run --")
        result = await runner.run(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            enabled_tools=enabled,
        )

        print("\n" + "=" * 70)
        print("RESULTADO")
        print("=" * 70)
        print(f"completed:    {result.completed}")
        print(f"turnos:       {result.turn_count}")
        print(f"tool calls:   {len(result.tool_calls)}")
        print(f"  sequencia:  {' -> '.join(result.tool_calls)}")
        print(f"custo total:  US$ {result.total_cost_usd:.4f}")
        if result.error:
            print(f"ERRO:         {result.error}")
        if result.completion_summary:
            print(f"\nSUMARIO:\n{result.completion_summary}")
        if result.completion_deliverables:
            print("\nDELIVERABLES:")
            for d in result.completion_deliverables:
                print(f"  - {d}")

        await wt.cleanup()
        await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
