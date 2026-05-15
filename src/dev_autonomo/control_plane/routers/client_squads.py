"""Router /client/squads: CRUD de squads escopadas pelo client do usuario.

Todos os endpoints exigem auth + contexto de client. SYSTEM_ADMIN pode
operar em qualquer client passando X-Client-Id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import (
    AgentInstanceStatus,
    AgentTier,
    SquadStatus,
    UserRole,
)
from dev_autonomo.control_plane.dependencies import (
    get_current_user,
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.squad import (
    AgentInstanceCreate,
    AgentInstancePublic,
    AgentInstanceUpdate,
    AgentPromptUpdate,
    ManifestPublic,
    ManifestUpdate,
    SquadCreate,
    SquadPublic,
    SquadUpdate,
)
from dev_autonomo.db.models import (
    AgentInstance,
    Client,
    Manifest,
    SkillTemplate,
    Squad,
    User,
)

router = APIRouter(prefix="/client/squads", tags=["client / squads"])


# Helpers de papel (apenas certos roles podem escrever)
_WRITE_ROLES = (UserRole.CLIENT_ADMIN, UserRole.SYSTEM_ADMIN)


def _ensure_can_write(role: UserRole) -> None:
    if role not in _WRITE_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"role {role} nao pode modificar; precisa de CLIENT_ADMIN",
        )


async def _get_squad_or_404(
    session: AsyncSession, client_id: UUID, squad_id: UUID
) -> Squad:
    squad = (
        await session.execute(
            select(Squad).where(Squad.id == squad_id, Squad.client_id == client_id)
        )
    ).scalar_one_or_none()
    if squad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="squad nao encontrada")
    return squad


# ---- Squad CRUD ----


@router.get("", response_model=list[SquadPublic])
async def list_squads(
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> list[Squad]:
    client, _ = ctx
    stmt = select(Squad).where(Squad.client_id == client.id).order_by(Squad.created_at.desc())
    return (await session.execute(stmt)).scalars().all()


@router.post("", response_model=SquadPublic, status_code=status.HTTP_201_CREATED)
async def create_squad(
    body: SquadCreate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Squad:
    client, role = ctx
    _ensure_can_write(role)

    existing = (
        await session.execute(
            select(Squad).where(Squad.client_id == client.id, Squad.slug == body.slug)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="slug ja em uso neste client")

    squad = Squad(
        client_id=client.id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        domain=body.domain,
        status=SquadStatus.PROVISIONING,
    )
    session.add(squad)
    await session.commit()
    await session.refresh(squad)
    return squad


@router.get("/{squad_id}", response_model=SquadPublic)
async def get_squad(
    squad_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Squad:
    client, _ = ctx
    return await _get_squad_or_404(session, client.id, squad_id)


@router.patch("/{squad_id}", response_model=SquadPublic)
async def update_squad(
    squad_id: UUID,
    body: SquadUpdate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Squad:
    client, role = ctx
    _ensure_can_write(role)
    squad = await _get_squad_or_404(session, client.id, squad_id)

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(squad, key, value)
    await session.commit()
    await session.refresh(squad)
    return squad


# ---- Manifest ----


@router.get("/{squad_id}/manifest", response_model=ManifestPublic)
async def get_squad_manifest(
    squad_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Manifest:
    client, _ = ctx
    squad = await _get_squad_or_404(session, client.id, squad_id)
    if squad.current_manifest_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="squad ainda nao tem manifest ativo"
        )
    manifest = await session.get(Manifest, squad.current_manifest_id)
    if manifest is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="manifest nao encontrado"
        )
    return manifest


@router.put("/{squad_id}/manifest", response_model=ManifestPublic, status_code=status.HTTP_201_CREATED)
async def update_squad_manifest(
    squad_id: UUID,
    body: ManifestUpdate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Manifest:
    """Cria uma nova VERSAO do manifest (manifestos sao imutaveis)."""
    client, role = ctx
    _ensure_can_write(role)
    squad = await _get_squad_or_404(session, client.id, squad_id)

    # Proxima versao
    last = (
        await session.execute(
            select(Manifest.version)
            .where(Manifest.squad_id == squad.id)
            .order_by(Manifest.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = (last or 0) + 1

    manifest = Manifest(
        client_id=client.id,
        squad_id=squad.id,
        version=next_version,
        content=body.content.model_dump(),
        created_by_user_id=current_user.id,
    )
    session.add(manifest)
    await session.flush()

    squad.current_manifest_id = manifest.id
    await session.commit()
    await session.refresh(manifest)
    return manifest


# ---- Agent instances ----


@router.get("/{squad_id}/agents", response_model=list[AgentInstancePublic])
async def list_agents(
    squad_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> list[AgentInstance]:
    client, _ = ctx
    await _get_squad_or_404(session, client.id, squad_id)
    stmt = (
        select(AgentInstance)
        .where(AgentInstance.squad_id == squad_id)
        .order_by(AgentInstance.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().all()


@router.post(
    "/{squad_id}/agents",
    response_model=AgentInstancePublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    squad_id: UUID,
    body: AgentInstanceCreate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> AgentInstance:
    client, role = ctx
    _ensure_can_write(role)
    squad = await _get_squad_or_404(session, client.id, squad_id)

    # Valida skill template (SYSTEM-level ou do mesmo client)
    tpl = (
        await session.execute(
            select(SkillTemplate).where(SkillTemplate.id == body.skill_template_id)
        )
    ).scalar_one_or_none()
    if tpl is None or not tpl.active:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="skill template nao encontrado ou inativo"
        )
    if tpl.client_id is not None and tpl.client_id != client.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="skill template pertence a outro client",
        )

    agent = AgentInstance(
        client_id=client.id,
        squad_id=squad.id,
        skill_template_id=tpl.id,
        name=body.name,
        domain_business=body.domain_business,
        status=AgentInstanceStatus.IDLE,
        config_overrides=body.config_overrides or {},
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.patch(
    "/{squad_id}/agents/{agent_id}", response_model=AgentInstancePublic
)
async def update_agent(
    squad_id: UUID,
    agent_id: UUID,
    body: AgentInstanceUpdate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> AgentInstance:
    client, role = ctx
    _ensure_can_write(role)
    await _get_squad_or_404(session, client.id, squad_id)

    agent = await session.get(AgentInstance, agent_id)
    if agent is None or agent.squad_id != squad_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agente nao encontrado")

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(agent, key, value)
    await session.commit()
    await session.refresh(agent)
    return agent


# Tiers obrigatorios no pipeline. Se sobrar 0 ativo daquele tier apos
# remocao/disable, bloqueia a operacao.
_REQUIRED_TIERS = (AgentTier.ARCHITECT, AgentTier.DEV)


async def _count_active_peers_of_tier(
    session: AsyncSession,
    squad_id: UUID,
    tier: AgentTier,
    exclude_agent_id: UUID,
) -> int:
    """Conta agentes ativos do mesmo tier na squad, excluindo o alvo."""
    stmt = (
        select(func.count(AgentInstance.id))
        .join(SkillTemplate, SkillTemplate.id == AgentInstance.skill_template_id)
        .where(
            AgentInstance.squad_id == squad_id,
            AgentInstance.id != exclude_agent_id,
            AgentInstance.status != AgentInstanceStatus.DISABLED,
            SkillTemplate.tier == tier,
        )
    )
    return (await session.execute(stmt)).scalar_one() or 0


@router.patch(
    "/{squad_id}/agents/{agent_id}/prompt",
    response_model=AgentInstancePublic,
)
async def update_agent_prompt(
    squad_id: UUID,
    agent_id: UUID,
    body: AgentPromptUpdate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> AgentInstance:
    """Edita prompt + modelo de um agente.

    Cria nova versao do SkillTemplate (client-scoped) com o prompt
    custom. Re-aponta o AgentInstance. anthropic_agent_id NAO eh
    copiado — re-provisionamento ocorre lazy na proxima execucao.
    """
    client, role = ctx
    _ensure_can_write(role)
    await _get_squad_or_404(session, client.id, squad_id)

    agent = await session.get(AgentInstance, agent_id)
    if agent is None or agent.squad_id != squad_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agente nao encontrado")
    if agent.status == AgentInstanceStatus.DISABLED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="agente desativado nao pode ser editado",
        )

    current_tpl = await session.get(SkillTemplate, agent.skill_template_id)
    if current_tpl is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="skill template do agente nao encontrado",
        )
    if current_tpl.client_id is not None and current_tpl.client_id != client.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="skill template pertence a outro client",
        )

    # Proxima versao para esse slug dentro deste client.
    last_version = (
        await session.execute(
            select(func.max(SkillTemplate.version)).where(
                SkillTemplate.client_id == client.id,
                SkillTemplate.slug == current_tpl.slug,
            )
        )
    ).scalar_one_or_none() or 0
    next_version = max(last_version, current_tpl.version) + 1

    new_tpl = SkillTemplate(
        client_id=client.id,
        slug=current_tpl.slug,
        name=current_tpl.name,
        description=current_tpl.description,
        version=next_version,
        tier=current_tpl.tier,
        model_alias=body.model_alias or current_tpl.model_alias,
        stack_primary=current_tpl.stack_primary,
        stack_secondary=current_tpl.stack_secondary,
        system_prompt_ref=current_tpl.system_prompt_ref,
        tools_enabled=current_tpl.tools_enabled,
        knowledge_partitions=current_tpl.knowledge_partitions,
        active=True,
        anthropic_agent_id=None,  # lazy reprovision
        system_prompt_template=body.system_prompt,
        template_variables=current_tpl.template_variables,
        parent_stack_profile_id=current_tpl.parent_stack_profile_id,
    )
    session.add(new_tpl)
    await session.flush()

    agent.skill_template_id = new_tpl.id
    # marca customizacao no config_overrides pra UI sinalizar "personalizado"
    overrides = dict(agent.config_overrides or {})
    overrides["system_prompt_custom_at"] = datetime.now(timezone.utc).isoformat()
    overrides["system_prompt_template_version"] = next_version
    agent.config_overrides = overrides

    await session.commit()
    await session.refresh(agent)
    return agent


@router.delete(
    "/{squad_id}/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_agent(
    squad_id: UUID,
    agent_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Soft delete: marca AgentInstance.status = DISABLED.

    Bloqueia se for o unico agente ativo de tier ARCHITECT ou DEV.
    BA/Reviewer/OnboardingAnalyst sao removiveis livremente.
    """
    client, role = ctx
    _ensure_can_write(role)
    await _get_squad_or_404(session, client.id, squad_id)

    agent = await session.get(AgentInstance, agent_id)
    if agent is None or agent.squad_id != squad_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agente nao encontrado")
    if agent.status == AgentInstanceStatus.DISABLED:
        # idempotente — ja esta desativado
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    tpl = await session.get(SkillTemplate, agent.skill_template_id)
    if tpl is not None and tpl.tier in _REQUIRED_TIERS:
        peers = await _count_active_peers_of_tier(
            session, squad_id, tpl.tier, exclude_agent_id=agent.id
        )
        if peers == 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"impossivel remover unico agente {tpl.tier.value} ativo. "
                    "Adicione outro agente desse tier antes de remover."
                ),
            )

    agent.status = AgentInstanceStatus.DISABLED
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
