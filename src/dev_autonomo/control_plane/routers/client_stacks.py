"""Router /client/squads/{id}/stacks — CRUD da entidade Stack.

Stack e a stack persistida na squad (paths, framework, convencoes).
Diferente de StackProfile (template global ja existente).

Endpoints:
- GET    /client/squads/{squad_id}/stacks         — lista stacks da squad
- POST   /client/squads/{squad_id}/stacks         — cria stack manual
- PATCH  /client/squads/{squad_id}/stacks/{id}    — edita stack existente
- DELETE /client/squads/{squad_id}/stacks/{id}    — arquiva stack (soft delete)

Stacks DETECTED sao criadas pelo onboarding_analyzer v2 (PR-3). Aqui
clientes podem listar, ajustar e criar manuais (status=MANUAL).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import StackStatus, UserRole
from dev_autonomo.control_plane.dependencies import require_client_context
from dev_autonomo.db.models import Client, Squad, Stack, StackProfile
from dev_autonomo.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client/squads", tags=["client-stacks"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StackPublic(BaseModel):
    id: UUID
    squad_id: UUID
    parent_stack_profile_id: UUID | None
    slug: str
    name: str
    paths: list[str]
    framework: str | None
    framework_version: str | None
    conventions: dict[str, Any]
    status: StackStatus
    detected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StackCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    paths: list[str] = Field(default_factory=list)
    framework: str | None = Field(None, max_length=128)
    framework_version: str | None = Field(None, max_length=64)
    conventions: dict[str, Any] = Field(default_factory=dict)
    parent_stack_profile_slug: str | None = Field(None, max_length=64)


class StackUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    paths: list[str] | None = None
    framework: str | None = Field(None, max_length=128)
    framework_version: str | None = Field(None, max_length=64)
    conventions: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_squad(
    session: AsyncSession, client: Client, squad_id: UUID,
) -> Squad:
    squad = (await session.execute(
        select(Squad).where(Squad.id == squad_id, Squad.client_id == client.id)
    )).scalar_one_or_none()
    if squad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="squad nao encontrada")
    return squad


def _require_admin(role: UserRole) -> None:
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="apenas client_admin pode modificar stacks da squad",
        )


async def _resolve_parent_profile(
    session: AsyncSession, slug: str | None,
) -> UUID | None:
    if slug is None:
        return None
    profile = (await session.execute(
        select(StackProfile).where(StackProfile.slug == slug)
    )).scalar_one_or_none()
    return profile.id if profile is not None else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{squad_id}/stacks", response_model=list[StackPublic])
async def list_stacks(
    squad_id: UUID,
    include_archived: bool = False,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> list[Stack]:
    """Lista stacks da squad. Por default exclui ARCHIVED."""
    client, _ = ctx
    await _resolve_squad(session, client, squad_id)

    stmt = select(Stack).where(Stack.squad_id == squad_id)
    if not include_archived:
        stmt = stmt.where(Stack.status != StackStatus.ARCHIVED)
    stmt = stmt.order_by(Stack.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/{squad_id}/stacks",
    response_model=StackPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_stack(
    squad_id: UUID,
    body: StackCreate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Stack:
    """Cria stack manual. Tipico: cliente quer declarar area que ainda
    nao existe no codigo (ex: vai comecar app mobile)."""
    client, role = ctx
    _require_admin(role)
    squad = await _resolve_squad(session, client, squad_id)

    existing = (await session.execute(
        select(Stack).where(
            Stack.squad_id == squad.id, Stack.slug == body.slug,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"stack '{body.slug}' ja existe nessa squad",
        )

    parent_id = await _resolve_parent_profile(session, body.parent_stack_profile_slug)

    stack = Stack(
        client_id=client.id,
        squad_id=squad.id,
        parent_stack_profile_id=parent_id,
        slug=body.slug,
        name=body.name,
        paths=body.paths,
        framework=body.framework,
        framework_version=body.framework_version,
        conventions=body.conventions,
        status=StackStatus.MANUAL,
        detected_at=None,
    )
    session.add(stack)
    await session.commit()
    await session.refresh(stack)
    return stack


@router.patch("/{squad_id}/stacks/{stack_id}", response_model=StackPublic)
async def update_stack(
    squad_id: UUID,
    stack_id: UUID,
    body: StackUpdate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Stack:
    """Edita campos mutaveis da stack. slug e immutavel (chave logica)."""
    client, role = ctx
    _require_admin(role)
    await _resolve_squad(session, client, squad_id)

    stack = (await session.execute(
        select(Stack).where(Stack.id == stack_id, Stack.squad_id == squad_id)
    )).scalar_one_or_none()
    if stack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="stack nao encontrada")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(stack, key, value)
    await session.commit()
    await session.refresh(stack)
    return stack


@router.delete(
    "/{squad_id}/stacks/{stack_id}",
    status_code=status.HTTP_200_OK,
    response_model=StackPublic,
)
async def archive_stack(
    squad_id: UUID,
    stack_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> Stack:
    """Soft delete — marca stack como ARCHIVED em vez de apagar.

    Stacks ARCHIVED ficam fora do roteamento de PR e da listagem default
    mas o registro sobrevive pra auditoria + retomada se mudar de ideia.
    """
    client, role = ctx
    _require_admin(role)
    await _resolve_squad(session, client, squad_id)

    stack = (await session.execute(
        select(Stack).where(Stack.id == stack_id, Stack.squad_id == squad_id)
    )).scalar_one_or_none()
    if stack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="stack nao encontrada")

    stack.status = StackStatus.ARCHIVED
    await session.commit()
    await session.refresh(stack)
    return stack
