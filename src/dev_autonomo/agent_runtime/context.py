"""Contexto compartilhado pra uma execução de agente (passa pra todas as tools)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.agent_runtime.enforcement import ManifestEnforcer
from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.knowledge.qdrant_client import QdrantKnowledgeStore
from dev_autonomo.knowledge.retriever import KnowledgeRetriever
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient


@dataclass
class AgentRunContext:
    """Tudo que uma execução de agente precisa pra rodar:
    identidade (client/squad/agent), task, recursos (session, retriever, etc),
    workspace de filesystem, e o enforcer.
    """

    # Identidade
    client_id: UUID
    squad_id: UUID
    agent_instance_id: UUID | None
    task_id: UUID | None

    # Recursos compartilhados
    session: AsyncSession
    claude: ClaudeClient
    voyage: VoyageEmbeddingClient
    qdrant: QdrantKnowledgeStore
    retriever: KnowledgeRetriever
    enforcer: ManifestEnforcer

    # Filesystem (worktree onde o agente trabalha)
    workspace_root: Path | None = None
    # Repo URL/label associado ao workspace (passa pelo enforcer.check_edit_file)
    workspace_repo: str | None = None

    # Flags de comportamento / feature-flags
    enable_auto_merge: bool = False  # proteção: merge automatico desabilitado por default

    # Estado mutavel da execução
    cost_usd_total: float = 0.0
    tools_invoked: list[str] = field(default_factory=list)
