"""Migra GITHUB_TOKEN e JIRA_API_TOKEN do .env para o banco como EncryptedSecret.

DESCARTAVEL: enquanto temos credenciais no .env. Quando todos os clientes
gerenciarem credenciais via painel, este script vai pro lixo.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from dev_autonomo.common.encryption import SecretEncryptor
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import Client, EncryptedSecret
from dev_autonomo.db.session import session_scope


async def upsert_secret(session, client_id, kind, name, value, encryptor):
    existing = (
        await session.execute(
            select(EncryptedSecret).where(
                EncryptedSecret.client_id == client_id,
                EncryptedSecret.kind == kind,
                EncryptedSecret.name == name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  = {kind.value:15s} '{name}' ja existe — pulando")
        return existing

    secret = EncryptedSecret(
        client_id=client_id,
        name=name,
        kind=kind,
        encrypted_value=encryptor.encrypt(value),
        last_rotated_at=datetime.now(tz=timezone.utc),
    )
    session.add(secret)
    print(f"  + {kind.value:15s} '{name}' criada")
    return secret


async def migrate():
    settings = get_settings()
    encryptor = SecretEncryptor()

    async with session_scope() as session:
        client = (
            await session.execute(select(Client).where(Client.slug == "reco-orbis"))
        ).scalar_one_or_none()
        if client is None:
            print("Cliente reco-orbis nao encontrado. Seed primeiro.")
            return
        print(f"Cliente alvo: {client.slug} ({client.id})\n")

        if settings.GITHUB_TOKEN:
            await upsert_secret(
                session,
                client.id,
                SecretKind.GITHUB_TOKEN,
                "main",
                settings.GITHUB_TOKEN.get_secret_value(),
                encryptor,
            )
        else:
            print("  AVISO: GITHUB_TOKEN ausente no .env, pulando")

        if settings.JIRA_API_TOKEN:
            await upsert_secret(
                session,
                client.id,
                SecretKind.JIRA_TOKEN,
                "main",
                settings.JIRA_API_TOKEN.get_secret_value(),
                encryptor,
            )
        else:
            print("  AVISO: JIRA_API_TOKEN ausente no .env, pulando")


if __name__ == "__main__":
    asyncio.run(migrate())
    print("\nMigracao concluida. Agora os tokens aparecem na aba Credenciais do cliente.")
