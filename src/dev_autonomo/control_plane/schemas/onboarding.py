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
    """GET /client/squads/{id}/onboarding-status.

    A partir do PR-3 do redesign, retorna estado granular da state machine
    do analyzer v2. Frontend (tela 2 viva) le current_step + step_label
    + scan_progress pra renderizar etapas, mensagem em primeira pessoa,
    e barra de progresso quando ha contadores mensuraveis.
    """

    task_id: UUID | None = None
    # status "high level" — frontend pode usar pra decidir tela: not_started
    # vai pra tela 1, in_progress mostra tela 2 viva, completed segue pra 3,
    # failed mostra erro inline com botao retry.
    status: Literal[
        "not_started", "in_progress", "completed", "failed", "cancelled",
    ] = "not_started"

    # Etapa atual da state machine (v2). None enquanto pendente.
    current_step: str | None = None
    # Mensagem em prosa primeira pessoa pra mostrar na tela 2.
    step_label: str | None = None

    # Contadores granulares — schema flexivel (depende da etapa atual).
    # Pode incluir: total_files, files_processed, chunks_total,
    # chunks_indexed, oa_iterations, embedding_cost_usd, etc.
    scan_progress: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    started_at: datetime | None = None
    manifest_ready_at: datetime | None = None
    closed_at: datetime | None = None

    # Mensagem de erro quando status=failed
    error_message: str | None = None


class CancelAnalysisResponse(BaseModel):
    """POST /client/squads/{id}/cancel-onboarding-analysis."""

    task_id: UUID
    previous_status: str
    status: Literal["cancelled", "already_finished"]


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
