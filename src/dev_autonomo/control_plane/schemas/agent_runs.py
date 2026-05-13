"""Schemas Pydantic de runs de agente — listagem + detalhe."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunItem(BaseModel):
    """Representa um run individual do agente (agrupado por task_id)."""

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    jira_issue_key: str | None = None
    title: str | None = None
    tool_calls_count: int = Field(ge=0)
    total_cost_usd: Decimal
    started_at: datetime          # MIN(occurred_at) do grupo
    ended_at: datetime | None = None            # MAX(occurred_at) do grupo
    status: Literal["completed", "failed", "in_progress"]


class AgentRunsPage(BaseModel):
    """Resposta paginada do endpoint de agent runs."""

    items: list[AgentRunItem]
    total: int
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)


class ExternalCallItem(BaseModel):
    """Chamada individual a um provedor externo (Anthropic/Voyage)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    provider: str
    kind: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost_usd: Decimal
    latency_ms: int | None = None
    request_id: str | None = None
    error: str | None = None


class AgentRunDetail(BaseModel):
    """Detalhe de UM run específico — agregados + timeline paginada + links externos.

    Os agregados (total_cost, tokens, etc.) refletem o RUN COMPLETO. A lista
    ``calls`` é paginada via ``calls_offset/limit/total``.

    ``jira_issue_url`` aponta direto para a issue Jira da Task (formato
    ``{workspace}/browse/{KEY}``) quando a key é uma issue real (LEO-N).
    Para runs sintéticos (chaves "PR-*", "HIST-*"), fica ``None``.

    ``pr_search_url`` aponta para a busca de PRs do repo que mencionam a
    issue key — útil pra encontrar o(s) PR(s) gerado(s) por aquele run sem
    persistir mapeamento explícito Task→PR.
    """

    task_id: UUID
    agent_instance_id: UUID
    title: str | None = None
    jira_issue_key: str | None = None
    jira_issue_url: str | None = None
    pr_search_url: str | None = None
    status: Literal["completed", "failed", "in_progress"]
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    tool_calls_count: int = Field(ge=0)
    total_cost_usd: Decimal
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    error_count: int = Field(ge=0, default=0)
    calls: list[ExternalCallItem]
    calls_total: int = Field(ge=0)
    calls_offset: int = Field(ge=0)
    calls_limit: int = Field(ge=1)
