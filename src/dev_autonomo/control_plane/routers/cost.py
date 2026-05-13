"""Routers de custo (admin + client).

- /admin/clients/{id}/cost: SYSTEM_ADMIN consulta custo agregado de um client.
- /admin/cost/by-client: SYSTEM_ADMIN compara custo entre clients.
- /client/cost/summary: cliente ve seu proprio custo (com markup ja aplicado
  no full_cost_brl).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.cost_calc import (
    CostBreakdown,
    cost_for_client_period,
)
from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_client_context,
    require_system_admin,
)
from dev_autonomo.control_plane.schemas.cost import (
    CostBreakdownResponse,
    CostByClientItem,
    CostPeriodResponse,
)
from dev_autonomo.db.models import Client, ExternalApiCall


def _default_period(days: int = 30) -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=days)
    return start, end


def _breakdown_to_response(b: CostBreakdown) -> CostBreakdownResponse:
    return CostBreakdownResponse(
        direct_cost_usd=b.direct_cost_usd,
        direct_cost_brl=b.direct_cost_brl,
        infra_overhead_brl=b.infra_overhead_brl,
        fixed_overhead_brl=b.fixed_overhead_brl,
        full_cost_brl=b.full_cost_brl,
        num_tasks=b.num_tasks,
        num_calls=b.num_calls,
        total_input_tokens=b.total_input_tokens,
        total_output_tokens=b.total_output_tokens,
    )


# ---- Admin: custo de um cliente ----

admin_router = APIRouter(
    prefix="/admin", tags=["admin / cost"], dependencies=[Depends(require_system_admin)]
)


@admin_router.get(
    "/clients/{client_id}/cost", response_model=CostPeriodResponse
)
async def admin_cost_for_client(
    client_id: UUID,
    period_start: date | None = Query(None),
    period_end: date | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> CostPeriodResponse:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="client nao encontrado")

    if period_start is None or period_end is None:
        period_start, period_end = _default_period()

    breakdown = await cost_for_client_period(session, client_id, period_start, period_end)
    return CostPeriodResponse(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
        breakdown=_breakdown_to_response(breakdown),
    )


@admin_router.get("/cost/by-client", response_model=list[CostByClientItem])
async def admin_cost_by_client(
    period_start: date | None = Query(None),
    period_end: date | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[CostByClientItem]:
    """Ranking de custo por cliente no periodo. Util pra visao executiva."""
    if period_start is None or period_end is None:
        period_start, period_end = _default_period()
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())

    # Pega top clients por custo USD direto
    stmt = (
        select(ExternalApiCall.client_id, func.sum(ExternalApiCall.cost_usd))
        .where(
            and_(
                ExternalApiCall.occurred_at >= start_dt,
                ExternalApiCall.occurred_at <= end_dt,
            )
        )
        .group_by(ExternalApiCall.client_id)
        .order_by(func.sum(ExternalApiCall.cost_usd).desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    items: list[CostByClientItem] = []
    for client_id, _ in rows:
        client = await session.get(Client, client_id)
        if client is None:
            continue
        b = await cost_for_client_period(session, client_id, period_start, period_end)
        items.append(
            CostByClientItem(
                client_id=client.id,
                client_slug=client.slug,
                client_name=client.name,
                breakdown=_breakdown_to_response(b),
            )
        )
    return items


# ---- Client: seu proprio custo ----

client_router = APIRouter(prefix="/client/cost", tags=["client / cost"])


@client_router.get("/summary", response_model=CostPeriodResponse)
async def client_cost_summary(
    period_start: date | None = Query(None),
    period_end: date | None = Query(None),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> CostPeriodResponse:
    client, _ = ctx
    if period_start is None or period_end is None:
        period_start, period_end = _default_period()
    b = await cost_for_client_period(session, client.id, period_start, period_end)
    return CostPeriodResponse(
        client_id=client.id,
        period_start=period_start,
        period_end=period_end,
        breakdown=_breakdown_to_response(b),
    )
