"""Common runner library for scripts/dev/run_*_task.py.

Centraliza a lógica de:
- Setup de logging
- Resolução de identidades (client, squad, agente) — opcionalmente provisiona o
  AgentInstance se um callable ``ensure_agent`` for fornecido
- Indexação inicial do Knowledge Hub (opcional, para Dev)
- Setup de worktree (opcional, para Dev)
- Construção do AgentRunContext
- Registro de tools + execução do AgentRunner
- Print padronizado do resultado

Os scripts run_*_task.py viram thin wrappers que apenas declaram uma ``TaskSpec``
e chamam ``run_task(spec, issue_key)``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.enforcement import ManifestEnforcer
from dev_autonomo.agent_runtime.toolset.base import ToolRegistry
from dev_autonomo.agent_runtime.toolset.basic import (
    RetrieveKnowledgeTool,
    SignalCompleteTool,
)
from dev_autonomo.agent_runtime.worker import AgentRunner
from dev_autonomo.agent_runtime.worktree import GitWorktreeManager
from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.common.credentials_store import get_secret
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.db.models import AgentInstance, Client, Squad
from dev_autonomo.db.session import session_scope
from dev_autonomo.knowledge.indexer import CodeIndexer
from dev_autonomo.knowledge.qdrant_client import (
    KnowledgePartition,
    QdrantKnowledgeStore,
)
from dev_autonomo.knowledge.retriever import KnowledgeRetriever
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DEFAULT_REPO_URL = "https://github.com/rlenzi/obris-dev-squad-agent"
DEFAULT_REPO_LOCAL = Path("/home/rubens/dev-autonomo-workspace/dev-autonomo")
DEFAULT_WORKTREE_CACHE = Path("/home/rubens/dev-autonomo-workspace/worktree-cache")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    """Configura logging padronizado para os scripts dev."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    for noisy in ("sqlalchemy.engine", "httpx", "httpcore", "voyage"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# TaskSpec
# ---------------------------------------------------------------------------


EnsureAgentFn = Callable[
    [AsyncSession, Client, Squad], Awaitable[AgentInstance]
]
UserPromptBuilder = Callable[[str], str]


@dataclass
class TaskSpec:
    """Especificação de como rodar um agente específico contra uma issue Jira.

    Campos obrigatórios:
        agent_name: nome do AgentInstance na squad (ex: "Dev Backend Plataforma").
        tools: lista de instâncias de tools (já criadas). Não inclua
            ``RetrieveKnowledgeTool`` nem ``SignalCompleteTool`` — são adicionadas
            automaticamente pelo runner.
        system_prompt OU system_prompt_path: pelo menos um deve estar setado.

    Campos opcionais que controlam comportamento:
        ensure_agent: callable opcional que provisiona o AgentInstance se ele
            não existir (ex: Reviewer/Architect que sobem on-demand).
        needs_workspace: True → cria worktree para o agente trabalhar com
            filesystem (Dev). False → ctx.workspace_root = None (Reviewer/Architect).
        needs_indexed_knowledge: True → garante que o repo está indexado no
            Knowledge Hub antes de rodar (Dev).
        user_prompt_builder: função que recebe issue_key e retorna o prompt
            do user. Default: prompt genérico.
    """

    agent_name: str
    tools: list[Any] = field(default_factory=list)

    # Prompt: usar UM destes (system_prompt_path tem prioridade se ambos)
    system_prompt: str = ""
    system_prompt_path: Path | None = None

    # Identidades — default = squad Plataforma do tenant dev-autonomo
    client_slug: str = "dev-autonomo"
    squad_slug: str = "plataforma"

    # Comportamento
    repo_url: str = DEFAULT_REPO_URL
    needs_workspace: bool = False
    needs_indexed_knowledge: bool = False
    branch_prefix: str = "agents/dev-backend"

    # Execução
    model: str = "claude-sonnet-4-6"
    max_turns: int = 30
    max_tokens_per_turn: int = 8192

    # Hooks
    ensure_agent: EnsureAgentFn | None = None
    user_prompt_builder: UserPromptBuilder = field(
        default=lambda issue: f"Sua task é a issue Jira {issue}. Siga seu fluxo padrão."
    )


# ---------------------------------------------------------------------------
# Resolução de identidades
# ---------------------------------------------------------------------------


async def _resolve_identities(
    session: AsyncSession, spec: TaskSpec
) -> tuple[Client, Squad, AgentInstance]:
    client = (
        await session.execute(select(Client).where(Client.slug == spec.client_slug))
    ).scalar_one()
    squad = (
        await session.execute(
            select(Squad).where(
                Squad.client_id == client.id, Squad.slug == spec.squad_slug
            )
        )
    ).scalar_one()

    agent_q = await session.execute(
        select(AgentInstance).where(
            AgentInstance.squad_id == squad.id,
            AgentInstance.name == spec.agent_name,
        )
    )
    agent = agent_q.scalar_one_or_none()

    if agent is None:
        if spec.ensure_agent is None:
            raise RuntimeError(
                f"AgentInstance '{spec.agent_name}' não encontrado na squad "
                f"'{squad.slug}' do cliente '{client.slug}'. Configure "
                f"spec.ensure_agent para provisionar automaticamente, "
                f"ou crie manualmente via seed_dev_data.py."
            )
        agent = await spec.ensure_agent(session, client, squad)
        await session.commit()

    return client, squad, agent


# ---------------------------------------------------------------------------
# Knowledge Hub
# ---------------------------------------------------------------------------


async def _ensure_indexed(squad_id: Any, client_id: Any, repo_url: str) -> None:
    """Indexa o repo local se ainda não há chunks na partição CODE da squad."""
    store = QdrantKnowledgeStore()
    name = store.collection_name(KnowledgePartition.CODE, squad_id)
    try:
        if await store._client.collection_exists(name):
            count = await store.count(KnowledgePartition.CODE, squad_id)
            if count > 0:
                print(f"  Knowledge hub: {count} chunks já indexados.")
                await store.close()
                return
    except Exception:
        pass

    print(f"  Indexando {DEFAULT_REPO_LOCAL} ...")
    voyage = VoyageEmbeddingClient()
    indexer = CodeIndexer(voyage=voyage)
    result = await indexer.index_repo(
        client_id=client_id,
        squad_id=squad_id,
        repo_path=DEFAULT_REPO_LOCAL,
        repo_label=repo_url + ".git",
    )
    print(
        f"  Indexado: {result.chunks_created} chunks, "
        f"US$ {result.embedding_cost_usd:.4f}, {result.duration_seconds:.1f}s"
    )
    await store.close()


# ---------------------------------------------------------------------------
# run_task — entrypoint principal
# ---------------------------------------------------------------------------


async def run_task(spec: TaskSpec, issue_key: str) -> None:
    """Executa o agente descrito por ``spec`` contra a issue ``issue_key``."""
    setup_logging()

    print("=" * 70)
    print(f"Task {issue_key} · {spec.agent_name}")
    print("=" * 70)

    async with session_scope() as session:
        client, squad, agent = await _resolve_identities(session, spec)

        print(f"\nCliente:  {client.name} ({client.slug})")
        print(f"Squad:    {squad.name}")
        print(f"Agente:   {agent.name}")
        print(f"Issue:    {issue_key}")

        # Knowledge Hub (Dev)
        worktree_handle = None
        workspace_root = None

        if spec.needs_indexed_knowledge:
            print("\n-- Knowledge Hub --")
            await _ensure_indexed(squad.id, client.id, spec.repo_url)

        # Worktree (Dev)
        if spec.needs_workspace:
            token = await get_secret(
                session, client_id=client.id, kind=SecretKind.GITHUB_TOKEN
            )
            await session.commit()
            print("\n-- Worktree --")
            mgr = GitWorktreeManager(cache_root=DEFAULT_WORKTREE_CACHE)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            slug_part = issue_key.lower().replace(" ", "-")
            branch = f"{spec.branch_prefix}/{slug_part}-{timestamp}"
            task_handle = f"task-{slug_part}-{timestamp}"
            worktree_handle = await mgr.checkout_for_task(
                client_id=client.id,
                repo_url=spec.repo_url,
                task_handle=task_handle,
                new_branch=branch,
                github_token=token,
            )
            workspace_root = worktree_handle.path
            print(f"  branch:    {worktree_handle.branch}")

        # AgentRunContext
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
            workspace_root=workspace_root,
            workspace_repo=spec.repo_url,
        )

        # Tools
        registry = ToolRegistry()
        # Tools sempre presentes
        registry.register(RetrieveKnowledgeTool())
        registry.register(SignalCompleteTool())
        # Tools específicas do spec
        for tool in spec.tools:
            registry.register(tool)
        enabled = [t.name for t in registry.tools.values()]

        # System prompt
        if spec.system_prompt_path is not None:
            system_prompt = spec.system_prompt_path.read_text(encoding="utf-8")
        elif spec.system_prompt:
            system_prompt = spec.system_prompt
        else:
            raise RuntimeError(
                "TaskSpec precisa de 'system_prompt' (str) ou 'system_prompt_path' (Path)"
            )

        user_prompt = spec.user_prompt_builder(issue_key)

        # Runner
        runner = AgentRunner(
            ctx=ctx,
            registry=registry,
            model=spec.model,
            max_turns=spec.max_turns,
            max_tokens_per_turn=spec.max_tokens_per_turn,
        )

        print("\n-- Agent run --")
        result = await runner.run(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            enabled_tools=enabled,
        )

        _print_result(result)

        # Cleanup
        if worktree_handle is not None:
            await worktree_handle.cleanup()
        await qdrant.close()


def _print_result(result: Any) -> None:
    """Imprime resumo padronizado do AgentRunResult."""
    print("\n" + "=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"completed:    {result.completed}")
    print(f"turnos:       {result.turn_count}")
    print(f"tool calls:   {len(result.tool_calls)}")
    if result.tool_calls:
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


# ---------------------------------------------------------------------------
# Helpers de CLI
# ---------------------------------------------------------------------------


def parse_issue_key(script_name: str = "run_task") -> str:
    """Extrai o issue_key de sys.argv[1] (uppercase + trim)."""
    if len(sys.argv) < 2:
        print(f"Uso: python -m scripts.dev.{script_name} <ISSUE-KEY>")
        sys.exit(1)
    return sys.argv[1].strip().upper()
