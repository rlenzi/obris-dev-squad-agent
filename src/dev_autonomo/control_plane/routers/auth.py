"""Router de autenticacao: login + refresh."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.control_plane.auth import (
    JWT_TTL_HOURS,
    create_access_token,
    verify_password,
)
from dev_autonomo.control_plane.dependencies import get_current_user, get_session
from dev_autonomo.control_plane.schemas.auth import LoginRequest, TokenResponse
from dev_autonomo.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()

    # mensagem generica pra nao revelar se email existe
    invalid = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="credenciais invalidas"
    )
    if user is None or not user.active or not user.hashed_password:
        raise invalid
    if not verify_password(body.password, user.hashed_password):
        raise invalid

    user.last_login_at = datetime.now(tz=UTC)
    await session.commit()

    token = create_access_token(
        user_id=user.id, email=user.email, is_system_admin=user.is_system_admin
    )
    return TokenResponse(
        access_token=token, expires_in_seconds=JWT_TTL_HOURS * 3600
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(current_user: User = Depends(get_current_user)) -> TokenResponse:
    """Renova o token de um usuario ja autenticado (mantem mesmo perfil)."""
    token = create_access_token(
        user_id=current_user.id,
        email=current_user.email,
        is_system_admin=current_user.is_system_admin,
    )
    return TokenResponse(access_token=token, expires_in_seconds=JWT_TTL_HOURS * 3600)
