"""Schemas Pydantic para o endpoint GET /clients/{cid}/agents/{aid}/runs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AgentRunPublic(BaseModel):
    """Representação pública de uma execução de agente (AgentRun)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    agent_instance_id: UUID
    task_id: UUID | None

    status: str
    started_at: datetime | None
    finished_at: datetime | None
    turn_count: int
    total_cost_usd: Decimal
    error: str | None

    created_at: datetime
    updated_at: datetime


class AgentRunsPage(BaseModel):
    """Página paginada de execuções de um agente."""

    items: list[AgentRunPublic]
    total: int
    offset: int
    limit: int
