"""Schemas Pydantic de listagem paginada de agent runs."""

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
    tool_calls_count: int = Field(ge=0)
    total_cost_usd: Decimal
    started_at: datetime          # MIN(occurred_at) do grupo
    ended_at: datetime | None = None            # MAX(occurred_at) do grupo
    status: Literal["completed", "failed", "in_progress"]


class AgentRunsPage(BaseModel):
    """Resposta paginada do endpoint de agent runs."""


    items: list[AgentRunItem]
    total: int        # total de runs distintos (para o frontend calcular páginas)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
