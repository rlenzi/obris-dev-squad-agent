"""Router admin: gestao de users de um cliente especifico.

Usado pelo wizard de novo cliente no painel admin pra criar o user
inicial CLIENT_ADMIN do tenant, e pra inspecao posterior.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_system_admin,
)
from dev_autonomo.control_plane.schemas.user import (
    AdminClientUserCreate,
    ClientUserPublic,
)
from dev_autonomo.control_plane.services.user_management import (
    UserManagementError,
    create_user_for_client,
    list_users_for_client,
)
from dev_autonomo.db.models import User

router = APIRouter(tags=["admin / users"], prefix="/admin")


@router.post(
    "/clients/{cid}/users",
    response_model=ClientUserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Cria user inicial pro tenant (system_admin)",
)
async def admin_create_client_user(
    cid: UUID,
    payload: AdminClientUserCreate,
    _admin: User = Depends(require_system_admin),
    session: AsyncSession = Depends(get_session),
) -> ClientUserPublic:
    try:
        user, membership = await create_user_for_client(
            session=session,
            client_id=cid,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            role=payload.role,
        )
    except UserManagementError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
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


@router.get(
    "/clients/{cid}/users",
    response_model=list[ClientUserPublic],
    summary="Lista users do tenant (system_admin)",
)
async def admin_list_client_users(
    cid: UUID,
    _admin: User = Depends(require_system_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ClientUserPublic]:
    rows = await list_users_for_client(session=session, client_id=cid)
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
