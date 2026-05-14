"""Roda o Dev em modo 'address review' contra um PR com REQUEST_CHANGES.

Diferente de ``run_platform_task`` que abre PR novo, este runner:
- Recebe pr_number como argv
- Detecta a branch do PR via GitHub API
- Faz checkout da branch existente (worktree)
- Roda Dev com prompt focado em LER os comentarios do Reviewer e
  produzir commits que respondam ao feedback
- NAO abre PR novo — push na mesma branch reusa o PR aberto

Uso:
    uv run python -m scripts.dev.run_dev_address_review 42

Fecha LEO-31: Reviewer<->Dev cycle.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime

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
    GitHubGetReviewCommentsTool,
    GitPushTool,
)
from dev_autonomo.agent_runtime.toolset.repo_checks import RunRepoCheckTool
from dev_autonomo.agent_runtime.worker import AgentRunner
from dev_autonomo.agent_runtime.worktree import GitWorktreeManager
from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.common.credentials_store import get_secret
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.db.models import AgentInstance, Client, Squad, Task
from dev_autonomo.db.session import session_scope
from dev_autonomo.knowledge.qdrant_client import QdrantKnowledgeStore
from dev_autonomo.knowledge.retriever import KnowledgeRetriever
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient
from dev_autonomo.mcp_clients.github_client import GitHubClient
from scripts.dev._runner_lib import DEFAULT_REPO_URL, DEFAULT_WORKTREE_CACHE

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
Voce e um Dev Backend Python+FastAPI senior na squad Plataforma do projeto
dev-autonomo. ESTE RUN E EM RESPOSTA A UM REQUEST_CHANGES DO REVIEWER em
um PR ja aberto. Sua missao e LER o feedback e responder com commits
adicionais na MESMA branch (sem abrir PR novo).

FLUXO OBRIGATORIO:
1. github_get_review_comments(pr_number=<numero do PR>) — pegue a ultima
   review REQUEST_CHANGES + comentarios inline (path+linha).
2. retrieve_knowledge se precisar de contexto extra do codebase.
3. read_file dos arquivos citados nos comentarios.
4. edit_file / create_file pra aplicar correcoes — apenas os arquivos
   citados pelo Reviewer, salvo se a fix forcar mexer em outro.
5. run_repo_check (lint, typecheck se tiver, test). Tem que passar.
6. git_status + git_diff pra confirmar o escopo.
7. git_commit com convencao: `fix(<escopo>): atender review do PR <N>`.
8. git_push pra mesma branch (PR existente atualiza automaticamente).
9. signal_complete com summary = "Atendeu review do PR #N: <lista de
   pontos endereçados>" + deliverables = ["commit <sha>", "comentarios
   endereçados: <N>"].

NAO abra PR novo. NAO mude a base. NAO faca rebase forcado. Apenas
commits adicionais na branch existente.

Se um comentario do Reviewer e ambiguo ou voce discorda tecnicamente,
NAO ignore — adicione um commit que ENDERECA o ponto OU comente no PR
explicando a divergencia (via git_commit message do tipo "chore(reply):
respondendo review LEO-X — <justificativa>").

CONVENCAO DE NOMES (igual run_platform_task):
  fix(<escopo>): <verbo> <o que>
Tipos: feat, fix, chore, docs, refactor, test, perf.
PT-BR no conteudo. Max 72 chars no title.
"""


def _user_prompt(pr_number: int) -> str:
    return (
        f"Atender ao REQUEST_CHANGES do Reviewer no PR #{pr_number}. "
        f"Use github_get_review_comments(pr_number={pr_number}) PRIMEIRO."
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    for noisy in ("sqlalchemy.engine", "httpx", "httpcore", "voyage"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if len(sys.argv) < 2:
        print("Uso: python -m scripts.dev.run_dev_address_review <pr_number>")
        sys.exit(1)
    pr_number = int(sys.argv[1])

    print("=" * 70)
    print(f"Address Review · PR #{pr_number}")
    print("=" * 70)

    async with session_scope() as session:
        client = (
            await session.execute(
                select(Client).where(Client.slug == "dev-autonomo")
            )
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

        gh_token = await get_secret(
            session, client_id=client.id, kind=SecretKind.GITHUB_TOKEN
        )
        await session.commit()

        # Descobre branch do PR
        repo_url = DEFAULT_REPO_URL
        owner, repo_name = repo_url.rstrip("/").split("/")[-2:]
        gh = GitHubClient(token=gh_token)
        pr = await gh.get_pull_request(owner, repo_name, pr_number)
        branch = pr["head_ref"]
        print(f"PR branch: {branch}")

        # Task local
        jira_key = f"PR-{pr_number}-review"
        existing = (
            await session.execute(
                select(Task).where(
                    Task.client_id == client.id,
                    Task.jira_issue_key == jira_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            task = Task(
                client_id=client.id,
                squad_id=squad.id,
                jira_workspace_url=client.jira_workspace_url,
                jira_issue_key=jira_key,
                title=f"Address review PR #{pr_number}",
                assigned_agent_id=agent.id,
            )
            session.add(task)
            await session.flush()
        else:
            task = existing
        await session.commit()

        # Worktree na branch EXISTENTE (nao cria nova)
        mgr = GitWorktreeManager(cache_root=DEFAULT_WORKTREE_CACHE)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_handle = f"address-pr{pr_number}-{timestamp}"
        worktree = await mgr.checkout_for_task(
            client_id=client.id,
            repo_url=repo_url,
            task_handle=task_handle,
            new_branch=None,
            checkout_existing_branch=branch,
            github_token=gh_token,
        )
        print(f"worktree: {worktree.path}")

        # Context
        voyage = VoyageEmbeddingClient(session=session)
        qdrant = QdrantKnowledgeStore()
        retriever = KnowledgeRetriever(
            session=session, voyage=voyage, qdrant=qdrant
        )
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
            task_id=task.id,
            session=session,
            claude=ClaudeClient(session=session),
            voyage=voyage,
            qdrant=qdrant,
            retriever=retriever,
            enforcer=enforcer,
            workspace_root=worktree.path,
            workspace_repo=repo_url,
        )

        registry = ToolRegistry()
        for tool in [
            RetrieveKnowledgeTool(),
            SignalCompleteTool(),
            ReadFileTool(),
            EditFileTool(),
            CreateFileTool(),
            GitStatusTool(),
            GitDiffTool(),
            GitCommitTool(),
            GitPushTool(),
            GitHubGetReviewCommentsTool(),
            RunRepoCheckTool(),
        ]:
            registry.register(tool)
        enabled = list(registry.tools.keys())

        runner = AgentRunner(
            ctx=ctx,
            registry=registry,
            model="claude-sonnet-4-6",
            max_turns=20,
            max_tokens_per_turn=8192,
        )

        result = await runner.run(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_user_prompt(pr_number),
            enabled_tools=enabled,
        )

        print("=" * 70)
        print(f"completed: {result.completed}")
        print(f"turnos:    {result.turn_count}")
        print(f"custo:     US$ {result.total_cost_usd:.4f}")
        if result.completion_summary:
            print(f"SUMARIO:\n{result.completion_summary}")

        await worktree.cleanup()
        await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
