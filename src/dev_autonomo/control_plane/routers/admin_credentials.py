"""Router /admin/clients/{id}/credentials: vault de tokens (GitHub, Jira, etc).

Todos endpoints exigem SYSTEM_ADMIN. O valor descriptografado NUNCA volta na
resposta — só metadata (kind, name, timestamps).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.encryption import SecretEncryptor
from dev_autonomo.control_plane.dependencies import (
    get_session,
    require_system_admin,
)
from dev_autonomo.control_plane.schemas.credential import (
    CredentialCreate,
    CredentialPublic,
    CredentialRotate,
)
from dev_autonomo.db.models import Client, EncryptedSecret

router = APIRouter(
    prefix="/admin/clients/{client_id}/credentials",
    tags=["admin / credentials"],
    dependencies=[Depends(require_system_admin)],
)


async def _get_client_or_404(session: AsyncSession, client_id: UUID) -> Client:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="client nao encontrado")
    return client


@router.get("", response_model=list[CredentialPublic])
async def list_credentials(
    client_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[EncryptedSecret]:
    await _get_client_or_404(session, client_id)
    stmt = (
        select(EncryptedSecret)
        .where(EncryptedSecret.client_id == client_id)
        .order_by(EncryptedSecret.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().all()


@router.post("", response_model=CredentialPublic, status_code=status.HTTP_201_CREATED)
async def create_credential(
    client_id: UUID,
    body: CredentialCreate,
    session: AsyncSession = Depends(get_session),
) -> EncryptedSecret:
    await _get_client_or_404(session, client_id)
    # Dedup por (client_id, kind, name)
    existing = (
        await session.execute(
            select(EncryptedSecret).where(
                EncryptedSecret.client_id == client_id,
                EncryptedSecret.kind == body.kind,
                EncryptedSecret.name == body.name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"ja existe credencial {body.kind.value} com nome '{body.name}'. "
            "Use /rotate para trocar o valor.",
        )

    encryptor = SecretEncryptor()
    cred = EncryptedSecret(
        client_id=client_id,
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
async def rotate_credential(
    client_id: UUID,
    credential_id: UUID,
    body: CredentialRotate,
    session: AsyncSession = Depends(get_session),
) -> EncryptedSecret:
    await _get_client_or_404(session, client_id)
    cred = await session.get(EncryptedSecret, credential_id)
    if cred is None or cred.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="credencial nao encontrada")

    encryptor = SecretEncryptor()
    cred.encrypted_value = encryptor.encrypt(body.value)
    cred.last_rotated_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(cred)
    return cred


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    client_id: UUID,
    credential_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_client_or_404(session, client_id)
    cred = await session.get(EncryptedSecret, credential_id)
    if cred is None or cred.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="credencial nao encontrada")
    await session.delete(cred)
    await session.commit()
