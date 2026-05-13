"""Schemas Pydantic para listagem de runs de um agente.

Um "run" representa uma execução agrupada por task_id na tabela
external_api_calls: agrega tool_calls, custo, timestamps e status.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunItem(BaseModel):
    """Item individual de run — representa uma task_id agrupada."""

    model_config = ConfigDict(from_attributes=False)

    task_id: UUID
    tool_calls_count: int
    total_cost_usd: Decimal
    started_at: datetime
    ended_at: datetime
    status: str = Field(..., description="'completed' ou 'failed'")


class AgentRunsPage(BaseModel):
    """Página paginada de runs de um agente."""

    model_config = ConfigDict(from_attributes=False)

    items: list[AgentRunItem]
    total: int = Field(..., description="Total de task_ids distintos (sem paginação)")
    offset: int
    limit: int
