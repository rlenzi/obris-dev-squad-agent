"""Router /admin/clients: CRUD de clientes + billing plan associado.

Todos os endpoints exigem SYSTEM_ADMIN.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import BillingPlanKind
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_system_admin,
)
from dev_autonomo.control_plane.schemas.client import (
    BillingPlanPublic,
    BillingPlanUpdate,
    ClientCreate,
    ClientPublic,
    ClientUpdate,
)
from dev_autonomo.db.models import Client, ClientBillingPlan

router = APIRouter(
    prefix="/admin/clients",
    tags=["admin / clients"],
    dependencies=[Depends(require_system_admin)],
)


@router.get("", response_model=list[ClientPublic])
async def list_clients(
    status_filter: str | None = Query(None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> list[Client]:
    stmt = select(Client).order_by(Client.created_at.desc())
    if status_filter:
        stmt = stmt.where(Client.status == status_filter)
    return (await session.execute(stmt)).scalars().all()


@router.post("", response_model=ClientPublic, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    session: AsyncSession = Depends(get_session),
) -> Client:
    existing = (
        await session.execute(select(Client).where(Client.slug == body.slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="slug ja em uso")

    client = Client(
        slug=body.slug,
        name=body.name,
        status="active",
        jira_workspace_url=body.jira_workspace_url,
        jira_email=body.jira_email,
    )
    session.add(client)
    await session.flush()

    # Cria billing plan com defaults
    plan = ClientBillingPlan(
        client_id=client.id,
        plan_kind=BillingPlanKind.HYBRID,
        base_fee_monthly_brl=Decimal("0"),
        included_quota_tokens=0,
        included_quota_tasks=0,
        overage_markup_pct=Decimal("0"),
        infra_overhead_pct=Decimal("20"),
        fixed_overhead_brl_per_task=Decimal("0"),
        usd_to_brl_rate=Decimal("5.0"),
    )
    session.add(plan)
    await session.commit()
    await session.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientPublic)
async def get_client(
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Client:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="client nao encontrado")
    return client


@router.patch("/{client_id}", response_model=ClientPublic)
async def update_client(
    client_id: UUID,
    body: ClientUpdate,
    session: AsyncSession = Depends(get_session),
) -> Client:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="client nao encontrado")

    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        new_status = data["status"]
        if new_status == "archived" and client.archived_at is None:
            client.archived_at = datetime.now(tz=UTC)
        elif new_status != "archived":
            client.archived_at = None
    for key, value in data.items():
        setattr(client, key, value)

    await session.commit()
    await session.refresh(client)
    return client


# ---- Billing plan ----


@router.get("/{client_id}/billing-plan", response_model=BillingPlanPublic)
async def get_billing_plan(
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ClientBillingPlan:
    plan = (
        await session.execute(
            select(ClientBillingPlan).where(ClientBillingPlan.client_id == client_id)
        )
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="billing plan nao configurado"
        )
    return plan


@router.put("/{client_id}/billing-plan", response_model=BillingPlanPublic)
async def update_billing_plan(
    client_id: UUID,
    body: BillingPlanUpdate,
    session: AsyncSession = Depends(get_session),
) -> ClientBillingPlan:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="client nao encontrado")

    plan = (
        await session.execute(
            select(ClientBillingPlan).where(ClientBillingPlan.client_id == client_id)
        )
    ).scalar_one_or_none()
    if plan is None:
        plan = ClientBillingPlan(
            client_id=client_id,
            plan_kind=BillingPlanKind.HYBRID,
        )
        session.add(plan)

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(plan, key, value)

    await session.commit()
    await session.refresh(plan)
    return plan
