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
from dev_autonomo.common.enums import SecretKind, UserRole
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
from dev_autonomo.services import anthropic_files_sync

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

    # Sync com Files API se for Jira ou GitHub (entrada do agente).
    await _sync_files_for_kind(session, client, body.kind)

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

    # Sync com Files API se for Jira ou GitHub.
    await _sync_files_for_kind(session, client, cred.kind)

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
    deleted_kind = cred.kind
    await session.delete(cred)
    await session.commit()

    # Apos deletar, sync Files API pode resultar em skipped (sem token);
    # ou ainda existem outras credenciais do mesmo kind. Re-sync resolve.
    await _sync_files_for_kind(session, client, deleted_kind)


@router.post("/sync-files")
async def force_sync_files(
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Forca resync de jira/github secrets pra Files API.

    Util pra recovery quando file_id foi deletado externamente, ou
    apos migracao quando colunas anthropic foram adicionadas mas
    credenciais ja existiam.
    """
    client, role = ctx
    _require_admin(role)
    results = await anthropic_files_sync.sync_all_for_client(session, client)
    await session.commit()
    return {
        "jira": {
            "file_id": results["jira"].file_id,
            "status": results["jira"].status,
            "error": results["jira"].error,
        },
        "github": {
            "file_id": results["github"].file_id,
            "status": results["github"].status,
            "error": results["github"].error,
        },
    }


async def _sync_files_for_kind(
    session: AsyncSession, client: Client, kind: SecretKind,
) -> None:
    """Dispara sync apenas pro kind alterado. Best-effort: nao quebra o
    request se Files API falhar (caller decide se loga/alerta)."""
    if kind == SecretKind.JIRA_TOKEN:
        await anthropic_files_sync.sync_jira_secrets(session, client)
        await session.commit()
    elif kind == SecretKind.GITHUB_TOKEN:
        await anthropic_files_sync.sync_github_secrets(session, client)
        await session.commit()
