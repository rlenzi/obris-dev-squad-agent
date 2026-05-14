"""Router cliente: gestao de users do proprio tenant.

Listagem aberta a qualquer membership; criacao/update restrito a CLIENT_
ADMIN do tenant.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.user import (
    ClientUserInvite,
    ClientUserPublic,
    ClientUserUpdate,
)
from dev_autonomo.control_plane.services.user_management import (
    UserManagementError,
    create_user_for_client,
    list_users_for_client,
    update_client_user,
)
from dev_autonomo.db.models import Client

router = APIRouter(tags=["client / users"])


@router.get(
    "/client/users",
    response_model=list[ClientUserPublic],
    summary="Lista users do tenant atual",
)
async def list_my_client_users(
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> list[ClientUserPublic]:
    client, _role = ctx
    rows = await list_users_for_client(session=session, client_id=client.id)
    return [
        ClientUserPublic(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=m.role,
            active=u.active,
            last_login_at=u.last_login_at,
            membership_id=m.id,
            created_at=u.created_at,
        )
        for u, m in rows
    ]


@router.post(
    "/client/users",
    response_model=ClientUserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Convida user no tenant atual (somente CLIENT_ADMIN)",
)
async def invite_client_user(
    payload: ClientUserInvite,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> ClientUserPublic:
    client, role = ctx
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="apenas CLIENT_ADMIN pode convidar users.",
        )

    try:
        user, membership = await create_user_for_client(
            session=session,
            client_id=client.id,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            role=payload.role,
        )
    except UserManagementError as err:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err
    await session.commit()

    return ClientUserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        active=user.active,
        last_login_at=user.last_login_at,
        membership_id=membership.id,
        created_at=user.created_at,
    )


@router.patch(
    "/client/users/{user_id}",
    response_model=ClientUserPublic,
    summary="Atualiza role/active de um user (somente CLIENT_ADMIN)",
)
async def update_my_client_user(
    user_id: UUID,
    payload: ClientUserUpdate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> ClientUserPublic:
    client, role = ctx
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="apenas CLIENT_ADMIN pode editar users.",
        )

    try:
        user, membership = await update_client_user(
            session=session,
            client_id=client.id,
            user_id=user_id,
            role=payload.role,
            active=payload.active,
        )
    except UserManagementError as err:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    await session.commit()

    return ClientUserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        active=user.active,
        last_login_at=user.last_login_at,
        membership_id=membership.id,
        created_at=user.created_at,
    )
