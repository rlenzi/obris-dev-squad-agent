"""GET /me: dados do usuario autenticado + memberships."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.dependencies import get_current_user, get_session
from dev_autonomo.control_plane.schemas.auth import (
    ClientMembershipPublic,
    MeResponse,
    UserPublic,
)
from dev_autonomo.db.models import Client, ClientMembership, User

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    stmt = (
        select(ClientMembership, Client)
        .join(Client, Client.id == ClientMembership.client_id)
        .where(ClientMembership.user_id == current_user.id)
    )
    rows = (await session.execute(stmt)).all()

    memberships = [
        ClientMembershipPublic(
            client_id=client.id,
            client_slug=client.slug,
            client_name=client.name,
            role=membership.role,
        )
        for membership, client in rows
    ]

    return MeResponse(
        user=UserPublic(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            is_system_admin=current_user.is_system_admin,
            active=current_user.active,
            created_at=current_user.created_at,
            last_login_at=current_user.last_login_at,
        ),
        memberships=memberships,
    )
