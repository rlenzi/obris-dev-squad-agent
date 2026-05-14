"""Schemas Pydantic de Squad, Manifest, SkillTemplate, AgentInstance."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dev_autonomo.common.enums import (
    AgentInstanceStatus,
    AgentTier,
    SquadStatus,
    TaskStatus,
)

# ---- Squad ----


class SquadCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(None, max_length=1024)
    domain: str | None = Field(None, max_length=128)


class SquadUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = Field(None, max_length=1024)
    domain: str | None = Field(None, max_length=128)
    status: SquadStatus | None = None


class SquadPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    slug: str
    name: str
    description: str | None
    domain: str | None
    status: SquadStatus
    current_manifest_id: UUID | None
    created_at: datetime
    updated_at: datetime


# ---- Manifest ----


class ManifestContent(BaseModel):
    """Estrutura do JSON do manifesto."""

    owns: dict[str, Any]
    humans_embedded: dict[str, Any] | None = None


class ManifestUpdate(BaseModel):
    content: ManifestContent


class ManifestPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    squad_id: UUID
    client_id: UUID
    version: int
    content: dict[str, Any]
    created_by_user_id: UUID | None
    created_at: datetime


# ---- SkillTemplate ----


class SkillTemplatePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID | None
    slug: str
    name: str
    description: str | None
    version: int
    tier: AgentTier
    model_alias: str
    stack_primary: dict[str, Any]
    stack_secondary: list[Any]
    system_prompt_ref: str
    tools_enabled: list[Any]
    knowledge_partitions: list[Any]
    active: bool


# ---- AgentInstance ----


class AgentInstanceCreate(BaseModel):
    skill_template_id: UUID
    name: str = Field(..., min_length=2, max_length=255)
    domain_business: str | None = Field(None, max_length=128)
    config_overrides: dict[str, Any] | None = None


class AgentInstanceUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    domain_business: str | None = Field(None, max_length=128)
    status: AgentInstanceStatus | None = None
    config_overrides: dict[str, Any] | None = None


class AgentInstancePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    squad_id: UUID
    skill_template_id: UUID
    name: str
    domain_business: str | None
    status: AgentInstanceStatus
    config_overrides: dict[str, Any]
    last_active_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentLastRunPublic(BaseModel):
    """Resumo da última run (Task) de um agente da squad."""

    agent_id: UUID
    last_run_status: TaskStatus | None
    last_run_at: datetime | None
