"""Schemas dos endpoints de onboarding analysis (Bloco E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RunAnalysisRequest(BaseModel):
    """POST /client/squads/{id}/run-onboarding-analysis body."""

    repo_urls: list[str] = Field(..., min_length=1, max_length=10)


class RunAnalysisResponse(BaseModel):
    """Identifica a task disparada (cliente faz polling depois)."""

    task_id: UUID
    status: Literal["started", "already_running"]


class OnboardingStatusResponse(BaseModel):
    """GET /client/squads/{id}/onboarding-status."""

    task_id: UUID | None
    status: Literal[
        "not_started", "pending", "extracting", "analyzing",
        "proposing", "completed", "failed",
    ]
    current_step: str
    progress_pct: int = Field(ge=0, le=100)
    manifest_ready_at: datetime | None = None
    error_message: str | None = None


class ManifestResponse(BaseModel):
    """GET /client/squads/{id}/onboarding-manifest — manifest cru lido do memory_store."""

    model_config = ConfigDict(extra="allow")

    raw: dict[str, Any]


class FinalizeSkillEntry(BaseModel):
    """1 entrada na lista que o cliente confirmou na tela 5."""

    # modo 1: skill catalog (slug global)
    catalog_skill_slug: str | None = None
    # modo 2: draft pra materializar (ja editado pelo cliente)
    draft_to_materialize: dict | None = None

    instance_name: str = Field("", description="Nome legivel do AgentInstance.")
    domain_business: str = "general"


class FinalizeSetupRequest(BaseModel):
    """POST /client/squads/{id}/finalize-setup body."""

    skills: list[FinalizeSkillEntry] = Field(..., min_length=1)


class FinalizeSetupResponse(BaseModel):
    """Identifica os AgentInstance criados."""

    agent_instance_ids: list[UUID]
    created_skill_ids: list[UUID] = Field(default_factory=list)
