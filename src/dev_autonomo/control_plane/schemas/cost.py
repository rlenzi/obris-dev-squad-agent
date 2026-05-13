"""Schemas Pydantic de custo/billing reports."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class CostBreakdownResponse(BaseModel):
    """Decomposicao de custo num escopo (client+periodo, ou task)."""

    direct_cost_usd: Decimal
    direct_cost_brl: Decimal
    infra_overhead_brl: Decimal
    fixed_overhead_brl: Decimal
    full_cost_brl: Decimal
    num_tasks: int
    num_calls: int
    total_input_tokens: int
    total_output_tokens: int


class CostPeriodResponse(BaseModel):
    """Custo agregado num periodo."""

    client_id: UUID
    period_start: date
    period_end: date
    breakdown: CostBreakdownResponse


class CostByClientItem(BaseModel):
    """Linha do ranking de custo por cliente (admin)."""

    client_id: UUID
    client_slug: str
    client_name: str
    breakdown: CostBreakdownResponse
