"""FastAPI dependencies: session, current_user, RBAC."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.auth import decode_access_token
from dev_autonomo.db.models import Client, ClientMembership, User
from dev_autonomo.db.session import AsyncSessionLocal


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Le `Authorization: Bearer <token>`, decodifica JWT, retorna User."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()

    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="token expirado") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"token invalido: {exc}") from exc

    user_id_raw = claims.get("sub")
    if not user_id_raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="claim 'sub' ausente")
    try:
        user_id = UUID(user_id_raw)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="sub invalido") from exc

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="usuario nao encontrado ou inativo")
    return user


async def require_system_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_system_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="endpoint exclusivo de SYSTEM_ADMIN"
        )
    return current_user


async def require_client_context(
    x_client_id: UUID | None = Header(None, alias="X-Client-Id"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> tuple[Client, UserRole]:
    """Resolve o cliente atual e o role do usuario nele.

    SYSTEM_ADMIN passa X-Client-Id para impersonar contexto de um cliente.
    Demais usuarios: pega o primeiro client_membership.

    Retorna (Client, role_no_client).
    """
    if current_user.is_system_admin:
        if x_client_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="SYSTEM_ADMIN precisa enviar header X-Client-Id",
            )
        client = (
            await session.execute(select(Client).where(Client.id == x_client_id))
        ).scalar_one_or_none()
        if client is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="client nao existe")
        return client, UserRole.SYSTEM_ADMIN

    # Usuario normal: busca membership ativo
    stmt = (
        select(ClientMembership, Client)
        .join(Client, Client.id == ClientMembership.client_id)
        .where(ClientMembership.user_id == current_user.id)
    )
    if x_client_id is not None:
        stmt = stmt.where(ClientMembership.client_id == x_client_id)
    memberships = (await session.execute(stmt)).all()

    if not memberships:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="usuario nao pertence a nenhum client"
        )
    if len(memberships) > 1 and x_client_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="usuario pertence a multiplos clients; envie X-Client-Id",
        )

    membership, client = memberships[0]
    return client, membership.role


def require_roles(*allowed: UserRole):
    """Cria dependency que exige role >= um dos allowed para o client atual."""

    async def _inner(
        ctx: tuple[Client, UserRole] = Depends(require_client_context),
    ) -> tuple[Client, UserRole]:
        _client, role = ctx
        if role == UserRole.SYSTEM_ADMIN:
            return ctx  # system admin passa em qualquer role check
        if role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"role {role} insuficiente; precisa de {[r.value for r in allowed]}",
            )
        return ctx

    return _inner
