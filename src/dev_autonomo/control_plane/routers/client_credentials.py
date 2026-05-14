"""Router /client/credentials: vault do proprio tenant (CLIENT_ADMIN).

Espelha admin_credentials mas atua sobre o cliente extraido do JWT
(require_client_context), nao via path. Listagem aberta a qualquer
membership; criar/rotacionar/deletar restrito a CLIENT_ADMIN.

O valor descriptografado nunca volta — so metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.encryption import SecretEncryptor
from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_client_context,
)
from dev_autonomo.control_plane.schemas.credential import (
    CredentialCreate,
    CredentialPublic,
    CredentialRotate,
)
from dev_autonomo.db.models import Client, EncryptedSecret

router = APIRouter(prefix="/client/credentials", tags=["client / credentials"])


def _require_admin(role: UserRole) -> None:
    if role != UserRole.CLIENT_ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="apenas CLIENT_ADMIN pode gerenciar credenciais.",
        )


@router.get("", response_model=list[CredentialPublic])
async def list_my_credentials(
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> list[EncryptedSecret]:
    client, _ = ctx
    stmt = (
        select(EncryptedSecret)
        .where(EncryptedSecret.client_id == client.id)
        .order_by(EncryptedSecret.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().all()


@router.post("", response_model=CredentialPublic, status_code=status.HTTP_201_CREATED)
async def create_my_credential(
    body: CredentialCreate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> EncryptedSecret:
    client, role = ctx
    _require_admin(role)

    existing = (
        await session.execute(
            select(EncryptedSecret).where(
                EncryptedSecret.client_id == client.id,
                EncryptedSecret.kind == body.kind,
                EncryptedSecret.name == body.name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"ja existe credencial {body.kind.value} com nome "
                f"'{body.name}'. Use /rotate para trocar o valor."
            ),
        )

    encryptor = SecretEncryptor()
    cred = EncryptedSecret(
        client_id=client.id,
        name=body.name,
        kind=body.kind,
        encrypted_value=encryptor.encrypt(body.value),
        last_rotated_at=datetime.now(tz=UTC),
    )
    session.add(cred)
    await session.commit()
    await session.refresh(cred)
    return cred


@router.post("/{credential_id}/rotate", response_model=CredentialPublic)
async def rotate_my_credential(
    credential_id: UUID,
    body: CredentialRotate,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> EncryptedSecret:
    client, role = ctx
    _require_admin(role)

    cred = await session.get(EncryptedSecret, credential_id)
    if cred is None or cred.client_id != client.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="credencial nao encontrada"
        )

    encryptor = SecretEncryptor()
    cred.encrypted_value = encryptor.encrypt(body.value)
    cred.last_rotated_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(cred)
    return cred


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_credential(
    credential_id: UUID,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> None:
    client, role = ctx
    _require_admin(role)

    cred = await session.get(EncryptedSecret, credential_id)
    if cred is None or cred.client_id != client.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="credencial nao encontrada"
        )
    await session.delete(cred)
    await session.commit()
