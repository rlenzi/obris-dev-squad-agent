"""Router /client/tasks/* — visão tenant-wide das tasks (S-2 do redesign)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import (
    OutcomeStatus, TaskStatus, UserRole,
)
from dev_autonomo.control_plane.dependencies import (
    get_session, require_client_context,
)
from dev_autonomo.db.models import (
    AgentInstance, Client, ExternalApiCall, Squad, Task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client/tasks", tags=["client / tasks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TaskListItem(BaseModel):
    id: UUID
    squad_id: UUID
    squad_slug: str | None
    jira_issue_key: str | None
    title: str
    status: TaskStatus
    current_step: str | None
    step_label: str | None
    assigned_agent_id: UUID | None
    started_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    pr_url: str | None
    cost_usd: float
    outcome_status: OutcomeStatus


class TasksListResponse(BaseModel):
    items: list[TaskListItem]
    total: int
    offset: int
    limit: int


class TaskTimelineEvent(BaseModel):
    """Evento na timeline do detalhe da task."""
    kind: str  # "step_started" / "step_completed" / "api_call" / "cancelled" / "failed"
    timestamp: datetime
    label: str
    detail: dict[str, Any] = Field(default_factory=dict)


class TaskDetailResponse(BaseModel):
    id: UUID
    squad_id: UUID
    squad_slug: str | None
    jira_workspace_url: str
    jira_issue_key: str | None
    title: str
    status: TaskStatus
    current_step: str | None
    step_label: str | None
    scan_progress: dict[str, Any]
    assigned_agent_id: UUID | None
    pr_url: str | None
    anthropic_session_id: str | None
    started_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    outcome_status: OutcomeStatus
    outcome_iterations: int
    cost_usd: float
    api_calls_count: int
    timeline: list[TaskTimelineEvent]


class DashboardSummary(BaseModel):
    in_progress_count: int
    completed_this_month: int
    completed_last_month: int
    cost_this_month: float
    cost_last_month: float
    active_agents: int
    failed_recent: int  # falhas nas últimas 24h
    recent_activity: list[TaskListItem]  # últimas 10 tasks (qualquer status)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=TasksListResponse)
async def list_tasks(
    squad_id: UUID | None = Query(None),
    agent_id: UUID | None = Query(None),
    task_status: TaskStatus | None = Query(None, alias="status"),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> TasksListResponse:
    """Lista tasks do tenant com filtros densos. Tenant-wide visão (D-04)."""
    client, _ = ctx

    filters = [Task.client_id == client.id]
    if squad_id is not None:
        filters.append(Task.squad_id == squad_id)
    if agent_id is not None:
        filters.append(Task.assigned_agent_id == agent_id)
    if task_status is not None:
        filters.append(Task.status == task_status)
    if since is not None:
        filters.append(Task.created_at >= since)
    if until is not None:
        filters.append(Task.created_at <= until)

    # Total count
    count_stmt = select(func.count(Task.id)).where(and_(*filters))
    total = (await session.execute(count_stmt)).scalar_one()

    # Itens paginados
    stmt = (
        select(Task, Squad.slug)
        .outerjoin(Squad, Task.squad_id == Squad.id)
        .where(and_(*filters))
        .order_by(desc(Task.created_at))
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    # Busca custos agregados por task em uma query só
    task_ids = [r[0].id for r in rows]
    cost_by_task: dict[UUID, float] = {}
    if task_ids:
        cost_stmt = (
            select(
                ExternalApiCall.task_id,
                func.coalesce(func.sum(ExternalApiCall.cost_usd), 0),
            )
            .where(ExternalApiCall.task_id.in_(task_ids))
            .group_by(ExternalApiCall.task_id)
        )
        for tid, total_cost in (await session.execute(cost_stmt)).all():
            cost_by_task[tid] = float(total_cost or 0)

    items = [
        TaskListItem(
            id=t.id, squad_id=t.squad_id, squad_slug=squad_slug,
            jira_issue_key=t.jira_issue_key, title=t.title,
            status=t.status, current_step=t.current_step,
            step_label=t.step_label,
            assigned_agent_id=t.assigned_agent_id,
            started_at=t.started_at, closed_at=t.closed_at,
            created_at=t.created_at, pr_url=t.pr_url,
            cost_usd=cost_by_task.get(t.id, 0.0),
            outcome_status=t.outcome_status,
        )
        for t, squad_slug in rows
    ]

    return TasksListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/dashboard-summary", response_model=DashboardSummary)
async def dashboard_summary(
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummary:
    """KPIs agregados pro dashboard principal (D-02)."""
    client, _ = ctx
    now = datetime.now(tz=timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)

    base = [Task.client_id == client.id]

    in_progress = (await session.execute(
        select(func.count(Task.id)).where(
            and_(*base, Task.status == TaskStatus.IN_PROGRESS),
        )
    )).scalar_one()

    completed_this = (await session.execute(
        select(func.count(Task.id)).where(
            and_(
                *base, Task.status == TaskStatus.DONE,
                Task.closed_at >= month_start,
            )
        )
    )).scalar_one()

    completed_last = (await session.execute(
        select(func.count(Task.id)).where(
            and_(
                *base, Task.status == TaskStatus.DONE,
                Task.closed_at >= last_month_start,
                Task.closed_at < month_start,
            )
        )
    )).scalar_one()

    cost_this = (await session.execute(
        select(func.coalesce(func.sum(ExternalApiCall.cost_usd), 0))
        .where(
            ExternalApiCall.client_id == client.id,
            ExternalApiCall.created_at >= month_start,
        )
    )).scalar_one()

    cost_last = (await session.execute(
        select(func.coalesce(func.sum(ExternalApiCall.cost_usd), 0))
        .where(
            ExternalApiCall.client_id == client.id,
            ExternalApiCall.created_at >= last_month_start,
            ExternalApiCall.created_at < month_start,
        )
    )).scalar_one()

    active_agents = (await session.execute(
        select(func.count(AgentInstance.id)).where(
            AgentInstance.client_id == client.id,
        )
    )).scalar_one()

    failed_24h = (await session.execute(
        select(func.count(Task.id)).where(
            and_(
                *base, Task.status == TaskStatus.FAILED,
                Task.updated_at >= now - timedelta(hours=24),
            )
        )
    )).scalar_one()

    # Atividade recente: últimas 10 tasks
    recent_stmt = (
        select(Task, Squad.slug)
        .outerjoin(Squad, Task.squad_id == Squad.id)
        .where(Task.client_id == client.id)
        .order_by(desc(Task.updated_at))
        .limit(10)
    )
    recent_rows = (await session.execute(recent_stmt)).all()
    task_ids = [t.id for t, _ in recent_rows]
    cost_by_task: dict[UUID, float] = {}
    if task_ids:
        cost_stmt = (
            select(
                ExternalApiCall.task_id,
                func.coalesce(func.sum(ExternalApiCall.cost_usd), 0),
            )
            .where(ExternalApiCall.task_id.in_(task_ids))
            .group_by(ExternalApiCall.task_id)
        )
        for tid, c in (await session.execute(cost_stmt)).all():
            cost_by_task[tid] = float(c or 0)

    recent = [
        TaskListItem(
            id=t.id, squad_id=t.squad_id, squad_slug=squad_slug,
            jira_issue_key=t.jira_issue_key, title=t.title,
            status=t.status, current_step=t.current_step,
            step_label=t.step_label,
            assigned_agent_id=t.assigned_agent_id,
            started_at=t.started_at, closed_at=t.closed_at,
            created_at=t.created_at, pr_url=t.pr_url,
            cost_usd=cost_by_task.get(t.id, 0.0),
            outcome_status=t.outcome_status,
        )
        for t, squad_slug in recent_rows
    ]

    return DashboardSummary(
        in_progress_count=in_progress,
        completed_this_month=completed_this,
        completed_last_month=completed_last,
        cost_this_month=float(cost_this or 0),
        cost_last_month=float(cost_last or 0),
        active_agents=active_agents,
        failed_recent=failed_24h,
        recent_activity=recent,
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task_detail(
    task_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> TaskDetailResponse:
    """Detalhe completo de uma task (D-05)."""
    client, _ = ctx
    stmt = (
        select(Task, Squad.slug)
        .outerjoin(Squad, Task.squad_id == Squad.id)
        .where(Task.id == task_id, Task.client_id == client.id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task nao encontrada")
    t, squad_slug = row

    # Total cost + api_calls_count
    cost_row = (await session.execute(
        select(
            func.coalesce(func.sum(ExternalApiCall.cost_usd), 0),
            func.count(ExternalApiCall.id),
        ).where(ExternalApiCall.task_id == task_id)
    )).one()
    total_cost = float(cost_row[0] or 0)
    api_count = cost_row[1] or 0

    # Timeline simples derivada de scan_progress + api_calls
    timeline: list[TaskTimelineEvent] = []
    scan = t.scan_progress or {}
    if scan.get("started_at"):
        try:
            timeline.append(TaskTimelineEvent(
                kind="started",
                timestamp=datetime.fromisoformat(scan["started_at"]),
                label="Task iniciada",
                detail={"mode": scan.get("mode", "repo")},
            ))
        except ValueError:
            pass
    if t.current_step:
        timeline.append(TaskTimelineEvent(
            kind="step_current",
            timestamp=t.updated_at,
            label=f"Etapa atual: {t.current_step}",
            detail={"step_label": t.step_label or ""},
        ))
    if scan.get("completed_at"):
        try:
            timeline.append(TaskTimelineEvent(
                kind="completed",
                timestamp=datetime.fromisoformat(scan["completed_at"]),
                label="Task concluída",
                detail={"stacks": scan.get("stacks_detected", 0)},
            ))
        except ValueError:
            pass
    if scan.get("failed_at"):
        try:
            timeline.append(TaskTimelineEvent(
                kind="failed",
                timestamp=datetime.fromisoformat(scan["failed_at"]),
                label="Task falhou",
                detail={"reason": scan.get("failure_reason", "")},
            ))
        except ValueError:
            pass
    if scan.get("cancelled_at"):
        try:
            timeline.append(TaskTimelineEvent(
                kind="cancelled",
                timestamp=datetime.fromisoformat(scan["cancelled_at"]),
                label="Task cancelada",
            ))
        except ValueError:
            pass

    return TaskDetailResponse(
        id=t.id, squad_id=t.squad_id, squad_slug=squad_slug,
        jira_workspace_url=t.jira_workspace_url, jira_issue_key=t.jira_issue_key,
        title=t.title, status=t.status, current_step=t.current_step,
        step_label=t.step_label, scan_progress=scan,
        assigned_agent_id=t.assigned_agent_id, pr_url=t.pr_url,
        anthropic_session_id=t.anthropic_session_id,
        started_at=t.started_at, closed_at=t.closed_at,
        created_at=t.created_at, updated_at=t.updated_at,
        outcome_status=t.outcome_status, outcome_iterations=t.outcome_iterations,
        cost_usd=total_cost, api_calls_count=api_count,
        timeline=timeline,
    )
