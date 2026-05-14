"""Schemas Pydantic do endpoint propose_skill_from_stack (Bloco D)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dev_autonomo.common.enums import AgentTier


class ProposeSkillsRequest(BaseModel):
    """Body do POST /client/squads/{id}/propose-skills."""

    manifest: dict = Field(
        ...,
        description=(
            "Manifest gerado pelo OA com schema: "
            '{"repos": [{"name", "primary_language", "framework", '
            '"build_command", "test_command", "lint_command", ...}, ...]}'
        ),
    )
    stack_slugs: list[str] = Field(
        ...,
        min_length=1,
        description="Lista de stack_profile slugs pra gerar drafts.",
    )


class SkillTemplateDraftPublic(BaseModel):
    """Draft retornado por propose-skills."""

    slug: str
    name: str
    description: str
    tier: AgentTier
    model_alias: str
    system_prompt: str
    tools_enabled: list[Any]
    stack_primary: dict[str, Any]
    stack_secondary: list[Any]
    knowledge_partitions: list[Any]
    template_variables: dict[str, Any]
    parent_stack_profile_id: UUID


class ProposeSkillsResponse(BaseModel):
    """Resposta com drafts + custo total da operacao."""

    drafts: list[SkillTemplateDraftPublic]
    api_call_cost_usd: Decimal
    input_tokens: int
    output_tokens: int


class CreateSkillFromDraftRequest(BaseModel):
    """Body do POST /client/squads/{id}/skills — cria skill a partir de draft."""

    draft: SkillTemplateDraftPublic
    edited_system_prompt: str | None = Field(
        None,
        description="Override opcional do system_prompt do draft (cliente editou).",
    )


class SkillTemplateCreated(BaseModel):
    """Resposta do POST de skill criado."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    tier: AgentTier
    model_alias: str
    anthropic_agent_id: str | None
    parent_stack_profile_id: UUID | None
