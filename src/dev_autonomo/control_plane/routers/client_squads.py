"""Router /client/squads: CRUD de squads escopadas pelo client do usuario.

Todos os endpoints exigem auth + contexto de client. SYSTEM_ADMIN pode
operar em qualquer client passando X-Client-Id.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import (
    AgentInstanceStatus,
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
    AgentLastRunPublic,
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
    Task,
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


@router.get("/{squad_id}/agents/last-runs", response_model=list[AgentLastRunPublic])
async def list_agents_last_run(
    squad_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> list[AgentLastRunPublic]:
    """Retorna a última run (Task) de cada agente da squad.

    Agentes sem nenhuma run retornam `last_run_status: null` e `last_run_at: null`.
    A query usa subquery com MAX(updated_at) por assigned_agent_id para evitar N+1.
    """
    client, _ = ctx
    await _get_squad_or_404(session, client.id, squad_id)

    # Busca todos os agentes da squad
    agents_stmt = (
        select(AgentInstance)
        .where(AgentInstance.squad_id == squad_id)
        .order_by(AgentInstance.created_at.desc())
    )
    agents: list[AgentInstance] = (await session.execute(agents_stmt)).scalars().all()

    if not agents:
        return []

    agent_ids = [a.id for a in agents]

    # Subquery: para cada assigned_agent_id, encontra o updated_at máximo
    latest_at_subq = (
        select(
            Task.assigned_agent_id,
            Task.updated_at,
            Task.status,
        )
        .where(Task.assigned_agent_id.in_(agent_ids))
        .order_by(Task.assigned_agent_id, Task.updated_at.desc())
        .distinct(Task.assigned_agent_id)
        .subquery()
    )

    runs_stmt = select(
        latest_at_subq.c.assigned_agent_id,
        latest_at_subq.c.status,
        latest_at_subq.c.updated_at,
    )
    rows = (await session.execute(runs_stmt)).all()

    # Indexa por agent_id para merge eficiente
    runs_by_agent: dict[Any, tuple[Any, Any]] = {
        row.assigned_agent_id: (row.status, row.updated_at) for row in rows
    }

    return [
        AgentLastRunPublic(
            agent_id=agent.id,
            last_run_status=runs_by_agent[agent.id][0] if agent.id in runs_by_agent else None,
            last_run_at=runs_by_agent[agent.id][1] if agent.id in runs_by_agent else None,
        )
        for agent in agents
    ]
