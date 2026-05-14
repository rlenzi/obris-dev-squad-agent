"""Router /client/squads/{id}/{propose-skills,skills} — Bloco D."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.skill_proposal import (
    CreateSkillFromDraftRequest,
    ProposeSkillsRequest,
    ProposeSkillsResponse,
    SkillTemplateCreated,
    SkillTemplateDraftPublic,
)
from dev_autonomo.db.models import Client, Squad
from dev_autonomo.services import skill_proposer
from dev_autonomo.services.skill_proposer import SkillTemplateDraft

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client/squads", tags=["client / skill proposer"])


def _require_client_admin(role: UserRole) -> None:
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="apenas CLIENT_ADMIN pode propor/criar skills.",
        )


async def _resolve_squad(
    session: AsyncSession, client: Client, squad_id: UUID,
) -> Squad:
    squad = (await session.execute(
        select(Squad).where(Squad.id == squad_id, Squad.client_id == client.id)
    )).scalar_one_or_none()
    if squad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="squad nao encontrada")
    return squad


@router.post(
    "/{squad_id}/propose-skills",
    response_model=ProposeSkillsResponse,
)
async def propose_skills(
    squad_id: UUID,
    body: ProposeSkillsRequest,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> ProposeSkillsResponse:
    """Gera drafts de skill_template baseado em stacks detectadas.

    Custo: ~US$ 0.05-0.20 por stack proposta (vai pra fatura via
    ExternalApiCall kind=SKILL_PROPOSAL).
    """
    client, role = ctx
    _require_client_admin(role)
    await _resolve_squad(session, client, squad_id)

    all_drafts: list[SkillTemplateDraft] = []
    total_cost = 0
    total_in = 0
    total_out = 0
    from decimal import Decimal as _D
    total_cost_d = _D("0")

    for stack_slug in body.stack_slugs:
        try:
            result = await skill_proposer.propose_skill_from_stack(
                session,
                stack_slug=stack_slug,
                manifest_json=body.manifest,
                client_id=client.id,
                task_id=None,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
        all_drafts.extend(result.drafts)
        total_cost_d += result.api_call_cost_usd
        total_in += result.input_tokens
        total_out += result.output_tokens

    await session.commit()

    drafts_public = [
        SkillTemplateDraftPublic(
            slug=d.slug,
            name=d.name,
            description=d.description,
            tier=d.tier,
            model_alias=d.model_alias,
            system_prompt=d.system_prompt,
            tools_enabled=d.tools_enabled,
            stack_primary=d.stack_primary,
            stack_secondary=d.stack_secondary,
            knowledge_partitions=d.knowledge_partitions,
            template_variables=d.template_variables,
            parent_stack_profile_id=d.parent_stack_profile_id,
        )
        for d in all_drafts
    ]
    return ProposeSkillsResponse(
        drafts=drafts_public,
        api_call_cost_usd=total_cost_d,
        input_tokens=total_in,
        output_tokens=total_out,
    )


@router.post(
    "/{squad_id}/skills",
    response_model=SkillTemplateCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_skill_from_draft(
    squad_id: UUID,
    body: CreateSkillFromDraftRequest,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> SkillTemplateCreated:
    """Materializa skill_template a partir do draft + provisiona agent."""
    client, role = ctx
    _require_client_admin(role)
    await _resolve_squad(session, client, squad_id)

    draft_obj = SkillTemplateDraft(
        slug=body.draft.slug,
        name=body.draft.name,
        description=body.draft.description,
        tier=body.draft.tier,
        model_alias=body.draft.model_alias,
        system_prompt=body.draft.system_prompt,
        tools_enabled=body.draft.tools_enabled,
        stack_primary=body.draft.stack_primary,
        stack_secondary=body.draft.stack_secondary,
        knowledge_partitions=body.draft.knowledge_partitions,
        template_variables=body.draft.template_variables,
        parent_stack_profile_id=body.draft.parent_stack_profile_id,
    )
    skill = await skill_proposer.materialize_skill_from_draft(
        session,
        draft=draft_obj,
        client_id=client.id,
        edited_system_prompt=body.edited_system_prompt,
    )
    await session.commit()
    return skill
