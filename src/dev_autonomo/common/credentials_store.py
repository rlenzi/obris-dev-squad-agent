"""Helper para ler credenciais criptografadas do vault.

Centraliza a descriptografia (Fernet) e atualiza last_used_at na linha
correspondente — util pra auditoria de tokens orfaos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.encryption import SecretEncryptor
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.db.models import EncryptedSecret


class CredentialNotFoundError(LookupError):
    pass


async def get_secret(
    session: AsyncSession,
    *,
    client_id: UUID,
    kind: SecretKind,
    name: str = "main",
    update_last_used: bool = True,
) -> str:
    """Retorna o valor descriptografado da credencial.

    Por padrao marca `last_used_at = now()` (commit pelo caller).
    """
    secret = (
        await session.execute(
            select(EncryptedSecret).where(
                EncryptedSecret.client_id == client_id,
                EncryptedSecret.kind == kind,
                EncryptedSecret.name == name,
            )
        )
    ).scalar_one_or_none()
    if secret is None:
        raise CredentialNotFoundError(
            f"credencial {kind.value} '{name}' nao encontrada para client {client_id}"
        )

    encryptor = SecretEncryptor()
    plaintext = encryptor.decrypt(secret.encrypted_value)
    if update_last_used:
        secret.last_used_at = datetime.now(tz=timezone.utc)
    return plaintext
