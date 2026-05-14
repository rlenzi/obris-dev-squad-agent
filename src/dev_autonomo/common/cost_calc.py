"""Calculo de custo TOTAL (direto + indireto) baseado em external_api_calls + billing plan.

Custo direto (USD) = sum(external_api_calls.cost_usd) filtrado por escopo.
Custo direto (BRL) = direto_usd * usd_to_brl_rate.
Custo infra (BRL) = direto_brl * infra_overhead_pct / 100.
Custo fixo (BRL) = fixed_overhead_brl_per_task * num_tasks.
Custo full (BRL) = direto_brl + infra_brl + fixed_brl.

Preco cobrado = custo_full * (1 + overage_markup_pct / 100), aplicado conforme
plano de billing (fase 2 elabora a regra exata de cobranca).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.db.models import ClientBillingPlan, ExternalApiCall, Task


@dataclass(slots=True)
class CostBreakdown:
    """Decomposicao do custo de um conjunto de chamadas API."""

    direct_cost_usd: Decimal
    direct_cost_brl: Decimal
    infra_overhead_brl: Decimal
    fixed_overhead_brl: Decimal
    full_cost_brl: Decimal
    num_tasks: int
    num_calls: int
    total_input_tokens: int
    total_output_tokens: int
    num_managed_sessions: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "direct_cost_usd": float(self.direct_cost_usd),
            "direct_cost_brl": float(self.direct_cost_brl),
            "infra_overhead_brl": float(self.infra_overhead_brl),
            "fixed_overhead_brl": float(self.fixed_overhead_brl),
            "full_cost_brl": float(self.full_cost_brl),
            "num_tasks": self.num_tasks,
            "num_calls": self.num_calls,
            "num_managed_sessions": self.num_managed_sessions,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
        }


async def get_billing_plan(session: AsyncSession, client_id: UUID) -> ClientBillingPlan | None:
    return (
        await session.execute(
            select(ClientBillingPlan).where(ClientBillingPlan.client_id == client_id)
        )
    ).scalar_one_or_none()


async def cost_for_task(
    session: AsyncSession, task_id: UUID, client_id: UUID
) -> CostBreakdown:
    """Custo total de uma task especifica."""
    plan = await get_billing_plan(session, client_id)
    if plan is None:
        plan_defaults = _default_plan_values()
    else:
        plan_defaults = (
            plan.infra_overhead_pct,
            plan.fixed_overhead_brl_per_task,
            plan.usd_to_brl_rate,
        )
    infra_pct, fixed_brl, fx = plan_defaults

    summary = (
        await session.execute(
            select(
                func.coalesce(func.sum(ExternalApiCall.cost_usd), Decimal("0")),
                func.count(ExternalApiCall.id),
                func.coalesce(func.sum(ExternalApiCall.input_tokens), 0),
                func.coalesce(func.sum(ExternalApiCall.output_tokens), 0),
            ).where(ExternalApiCall.task_id == task_id)
        )
    ).one()
    direct_usd, n_calls, in_tokens, out_tokens = summary

    return _compute_breakdown(
        direct_cost_usd=direct_usd,
        num_tasks=1,
        num_calls=n_calls,
        in_tokens=in_tokens,
        out_tokens=out_tokens,
        infra_overhead_pct=infra_pct,
        fixed_overhead_brl_per_task=fixed_brl,
        usd_to_brl_rate=fx,
    )


async def cost_for_client_period(
    session: AsyncSession,
    client_id: UUID,
    period_start: date,
    period_end: date,
) -> CostBreakdown:
    """Custo de um cliente num periodo (mes de billing)."""
    plan = await get_billing_plan(session, client_id)
    if plan is None:
        infra_pct, fixed_brl, fx = _default_plan_values()
    else:
        infra_pct, fixed_brl, fx = (
            plan.infra_overhead_pct,
            plan.fixed_overhead_brl_per_task,
            plan.usd_to_brl_rate,
        )

    # Soma de chamadas no periodo
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())
    summary = (
        await session.execute(
            select(
                func.coalesce(func.sum(ExternalApiCall.cost_usd), Decimal("0")),
                func.count(ExternalApiCall.id),
                func.coalesce(func.sum(ExternalApiCall.input_tokens), 0),
                func.coalesce(func.sum(ExternalApiCall.output_tokens), 0),
            ).where(
                and_(
                    ExternalApiCall.client_id == client_id,
                    ExternalApiCall.occurred_at >= start_dt,
                    ExternalApiCall.occurred_at <= end_dt,
                )
            )
        )
    ).one()
    direct_usd, n_calls, in_tokens, out_tokens = summary

    # Quantidade de tasks fechadas no periodo
    n_tasks = (
        await session.execute(
            select(func.count(Task.id)).where(
                and_(
                    Task.client_id == client_id,
                    Task.closed_at.is_not(None),
                    Task.closed_at >= start_dt,
                    Task.closed_at <= end_dt,
                )
            )
        )
    ).scalar_one()

    # Sessions Managed Agents (subset de num_calls com request_id no
    # padrao "sesn_..." — managed_runner usa session_id como request_id).
    n_managed_sessions = (
        await session.execute(
            select(func.count(ExternalApiCall.id)).where(
                and_(
                    ExternalApiCall.client_id == client_id,
                    ExternalApiCall.occurred_at >= start_dt,
                    ExternalApiCall.occurred_at <= end_dt,
                    ExternalApiCall.request_id.like("sesn_%"),
                )
            )
        )
    ).scalar_one()

    return _compute_breakdown(
        direct_cost_usd=direct_usd,
        num_tasks=int(n_tasks or 0),
        num_calls=int(n_calls or 0),
        num_managed_sessions=int(n_managed_sessions or 0),
        in_tokens=int(in_tokens or 0),
        out_tokens=int(out_tokens or 0),
        infra_overhead_pct=infra_pct,
        fixed_overhead_brl_per_task=fixed_brl,
        usd_to_brl_rate=fx,
    )


# ---- Helpers ----


def _default_plan_values() -> tuple[Decimal, Decimal, Decimal]:
    """Defaults caso o cliente nao tenha plano configurado."""
    return Decimal("20"), Decimal("0"), Decimal("5.0")


def _compute_breakdown(
    *,
    direct_cost_usd: Decimal,
    num_tasks: int,
    num_calls: int,
    in_tokens: int,
    out_tokens: int,
    infra_overhead_pct: Decimal,
    fixed_overhead_brl_per_task: Decimal,
    usd_to_brl_rate: Decimal,
    num_managed_sessions: int = 0,
) -> CostBreakdown:
    direct_brl = (direct_cost_usd * usd_to_brl_rate).quantize(Decimal("0.01"))
    infra_brl = (direct_brl * infra_overhead_pct / Decimal("100")).quantize(Decimal("0.01"))
    fixed_brl = (fixed_overhead_brl_per_task * Decimal(num_tasks)).quantize(Decimal("0.01"))
    full_brl = direct_brl + infra_brl + fixed_brl
    return CostBreakdown(
        direct_cost_usd=direct_cost_usd.quantize(Decimal("0.000001")),
        direct_cost_brl=direct_brl,
        infra_overhead_brl=infra_brl,
        fixed_overhead_brl=fixed_brl,
        full_cost_brl=full_brl,
        num_tasks=num_tasks,
        num_calls=num_calls,
        num_managed_sessions=num_managed_sessions,
        total_input_tokens=int(in_tokens),
        total_output_tokens=int(out_tokens),
    )
