"""Schemas Pydantic de Client e BillingPlan."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from dev_autonomo.common.enums import BillingPlanKind


# ---- Client ----


class ClientCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(..., min_length=2, max_length=255)
    jira_workspace_url: str | None = Field(None, max_length=255)
    jira_email: EmailStr | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    status: str | None = Field(None, pattern=r"^(active|paused|archived)$")
    jira_workspace_url: str | None = Field(None, max_length=255)
    jira_email: EmailStr | None = None


class ClientPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    status: str
    jira_workspace_url: str | None
    jira_email: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


# ---- BillingPlan ----


class BillingPlanUpdate(BaseModel):
    plan_kind: BillingPlanKind | None = None
    base_fee_monthly_brl: Decimal | None = Field(None, ge=0)
    included_quota_tokens: int | None = Field(None, ge=0)
    included_quota_tasks: int | None = Field(None, ge=0)
    overage_markup_pct: Decimal | None = Field(None, ge=0)
    infra_overhead_pct: Decimal | None = Field(None, ge=0)
    fixed_overhead_brl_per_task: Decimal | None = Field(None, ge=0)
    usd_to_brl_rate: Decimal | None = Field(None, gt=0)


class BillingPlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    client_id: UUID
    plan_kind: BillingPlanKind
    base_fee_monthly_brl: Decimal
    included_quota_tokens: int
    included_quota_tasks: int
    overage_markup_pct: Decimal
    infra_overhead_pct: Decimal
    fixed_overhead_brl_per_task: Decimal
    usd_to_brl_rate: Decimal
    starts_at: datetime
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime
