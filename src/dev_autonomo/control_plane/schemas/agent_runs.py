"""Schemas Pydantic de listagem paginada de agent runs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AgentRunItem(BaseModel):
    """Representa um run individual do agente (agrupado por task_id)."""

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    tool_calls_count: int
    total_cost_usd: Decimal
    started_at: datetime          # MIN(occurred_at) do grupo
    ended_at: datetime            # MAX(occurred_at) do grupo
    status: Literal["completed", "failed", "in_progress"]


class AgentRunsPage(BaseModel):
    """Resposta paginada do endpoint de agent runs."""

    model_config = ConfigDict(from_attributes=True)

    items: list[AgentRunItem]
    total: int        # total de runs distintos (para o frontend calcular páginas)
    offset: int
    limit: int
