"""Router /skill-templates: lista templates disponiveis para o usuario.

Retorna:
- SYSTEM-level templates (client_id IS NULL) — visiveis a todos
- Templates do client atual do usuario (se aplicavel)

SYSTEM_ADMIN pode usar /admin/skill-templates (futuro) para CRUD.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import AgentTier, UserRole
from dev_autonomo.control_plane.dependencies import (
    get_current_user,
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.squad import SkillTemplatePublic
from dev_autonomo.db.models import Client, SkillTemplate, User

router = APIRouter(prefix="/skill-templates", tags=["skill templates"])


@router.get("", response_model=list[SkillTemplatePublic])
async def list_skill_templates(
    tier: AgentTier | None = None,
    only_active: bool = True,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SkillTemplate]:
    """Lista templates: SYSTEM-level + do client do usuario.

    Para SYSTEM_ADMIN sem X-Client-Id, retorna SOMENTE SYSTEM-level.
    """
    # Resolve client_id do usuario se houver
    client_filter = SkillTemplate.client_id.is_(None)  # SYSTEM-level por default

    if not current_user.is_system_admin:
        # Pega o(s) client(s) do usuario
        from dev_autonomo.db.models import ClientMembership

        client_ids = (
            await session.execute(
                select(ClientMembership.client_id).where(
                    ClientMembership.user_id == current_user.id
                )
            )
        ).scalars().all()
        if client_ids:
            client_filter = or_(
                SkillTemplate.client_id.is_(None),
                SkillTemplate.client_id.in_(client_ids),
            )

    stmt = select(SkillTemplate).where(client_filter)
    if tier is not None:
        stmt = stmt.where(SkillTemplate.tier == tier)
    if only_active:
        stmt = stmt.where(SkillTemplate.active.is_(True))
    stmt = stmt.order_by(SkillTemplate.tier, SkillTemplate.name)
    return (await session.execute(stmt)).scalars().all()


@router.get("/{template_id}", response_model=SkillTemplatePublic)
async def get_skill_template(
    template_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillTemplate:
    tpl = await session.get(SkillTemplate, template_id)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="template nao encontrado")

    # Authorization: SYSTEM-level (NULL) visivel a todos; client-specific exige
    # pertencer ao client
    if tpl.client_id is not None and not current_user.is_system_admin:
        from dev_autonomo.db.models import ClientMembership

        is_member = (
            await session.execute(
                select(ClientMembership).where(
                    ClientMembership.user_id == current_user.id,
                    ClientMembership.client_id == tpl.client_id,
                )
            )
        ).scalar_one_or_none()
        if is_member is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="template pertence a outro client"
            )
    return tpl
