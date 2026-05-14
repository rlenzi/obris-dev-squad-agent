"""Sincroniza secrets do client com Files API da Anthropic.

Cada cliente que tem credenciais Jira/GitHub tem 1 arquivo correspondente
no Files API com seus tokens em formato ``.env``. Esse arquivo e usado
como ``resources=[{type:"file", file_id, mount_path:"/mnt/secrets/jira.env"}]``
nas sessions disparadas via managed_runner.

Lifecycle:
- ``sync_jira_secrets`` — chamado apos create/rotate de credencial Jira.
  Re-uploads ``.env`` contendo JIRA_BASE_URL + JIRA_EMAIL + JIRA_API_TOKEN,
  atualiza ``clients.jira_secrets_file_id``, e deleta o file_id antigo.
- ``sync_github_secrets`` — idem para GitHub. Apenas GITHUB_TOKEN
  (URL/repo vem do contexto da squad).
- Idempotente: roda novamente sem token muda nao gera lixo.
- Threadsafe a nivel de DB: usa transaction explicit; quem chama
  controla o commit.

Para uso pelo painel cliente:
- Endpoint POST /client/credentials/sync-files chama as 2 funcoes.
- Hook automatico: routers de create/rotate de credencial chamam
  apos commit local.

Notas de seguranca:
- Tokens descriptografados vivem em memoria do processo apenas durante
  a chamada. Sao enviados pra Anthropic Files API (encrypted in transit,
  encrypted at rest segundo a doc).
- File ID nao expoe conteudo — listing publico via Anthropic e safe.
- Se cliente cancelar/remover credencial, deletar file_id correspondente
  imediatamente.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.encryption import SecretEncryptor
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.config import get_settings
from dev_autonomo.db.models import Client, EncryptedSecret

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FilesSyncResult:
    """Resultado de um sync individual (jira ou github)."""

    file_id: str | None
    previous_file_id: str | None = None
    status: str = "ok"  # ok | skipped_no_token | failed | no_change
    error: str | None = None


def _build_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_settings().ANTHROPIC_API_KEY.get_secret_value()
    )


async def _decrypt_credential_for(
    session: AsyncSession, client_id, kind: SecretKind
) -> str | None:
    """Busca credencial daquele kind no cliente e retorna valor descriptografado."""
    stmt = (
        select(EncryptedSecret)
        .where(
            EncryptedSecret.client_id == client_id,
            EncryptedSecret.kind == kind,
        )
        .order_by(EncryptedSecret.created_at.desc())
        .limit(1)
    )
    cred = (await session.execute(stmt)).scalar_one_or_none()
    if cred is None:
        return None
    return SecretEncryptor().decrypt(cred.encrypted_value)


def _upload_env_file(
    anth: anthropic.Anthropic, filename: str, content: str
) -> str:
    """Upload .env content e retorna file_id."""
    file_obj = (filename, io.BytesIO(content.encode()), "text/plain")
    f = anth.beta.files.upload(file=file_obj)
    return f.id


def _safe_delete_file(anth: anthropic.Anthropic, file_id: str) -> None:
    """Delete file_id ignorando erros (idempotente)."""
    try:
        anth.beta.files.delete(file_id)
    except Exception as exc:
        logger.warning(
            "files_sync: delete file_id=%s falhou (ignorando): %s",
            file_id, exc,
        )


async def sync_jira_secrets(
    session: AsyncSession, client: Client,
    anth_client: anthropic.Anthropic | None = None,
) -> FilesSyncResult:
    """Sync .env Jira do cliente com Files API.

    Pre-req: client.jira_workspace_url, client.jira_email setados + 1
    EncryptedSecret com kind=jira_token.
    """
    if not client.jira_workspace_url or not client.jira_email:
        return FilesSyncResult(
            file_id=client.jira_secrets_file_id,
            status="skipped_no_token",
            error="jira_workspace_url ou jira_email ausente no client.",
        )

    token = await _decrypt_credential_for(session, client.id, SecretKind.JIRA_TOKEN)
    if not token:
        return FilesSyncResult(
            file_id=client.jira_secrets_file_id,
            status="skipped_no_token",
            error="nenhuma credencial JIRA_TOKEN encontrada.",
        )

    content = (
        f"export JIRA_BASE_URL='{client.jira_workspace_url}'\n"
        f"export JIRA_EMAIL='{client.jira_email}'\n"
        f"export JIRA_API_TOKEN='{token}'\n"
    )

    anth = anth_client or _build_anthropic_client()
    previous = client.jira_secrets_file_id

    try:
        new_file_id = _upload_env_file(anth, "jira.env", content)
    except Exception as exc:
        logger.exception("files_sync: upload jira falhou client=%s", client.slug)
        return FilesSyncResult(
            file_id=previous, previous_file_id=previous, status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )

    client.jira_secrets_file_id = new_file_id
    await session.flush()

    # Delete antigo apos sucesso do novo.
    if previous and previous != new_file_id:
        _safe_delete_file(anth, previous)

    logger.info(
        "files_sync: jira sincronizada client=%s new=%s (prev=%s)",
        client.slug, new_file_id, previous,
    )
    return FilesSyncResult(file_id=new_file_id, previous_file_id=previous, status="ok")


async def sync_github_secrets(
    session: AsyncSession, client: Client,
    anth_client: anthropic.Anthropic | None = None,
) -> FilesSyncResult:
    """Sync .env GitHub do cliente com Files API.

    Mantido por compat — caminho preferencial e usar
    github_repository resource direto (token embedded no resource).
    """
    token = await _decrypt_credential_for(session, client.id, SecretKind.GITHUB_TOKEN)
    if not token:
        return FilesSyncResult(
            file_id=client.github_secrets_file_id,
            status="skipped_no_token",
            error="nenhuma credencial GITHUB_TOKEN encontrada.",
        )

    content = f"export GITHUB_TOKEN='{token}'\n"

    anth = anth_client or _build_anthropic_client()
    previous = client.github_secrets_file_id

    try:
        new_file_id = _upload_env_file(anth, "github.env", content)
    except Exception as exc:
        logger.exception("files_sync: upload github falhou client=%s", client.slug)
        return FilesSyncResult(
            file_id=previous, previous_file_id=previous, status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )

    client.github_secrets_file_id = new_file_id
    await session.flush()

    if previous and previous != new_file_id:
        _safe_delete_file(anth, previous)

    logger.info(
        "files_sync: github sincronizada client=%s new=%s (prev=%s)",
        client.slug, new_file_id, previous,
    )
    return FilesSyncResult(file_id=new_file_id, previous_file_id=previous, status="ok")


async def sync_all_for_client(
    session: AsyncSession, client: Client,
    anth_client: anthropic.Anthropic | None = None,
) -> dict[str, FilesSyncResult]:
    """Conveniente: sync Jira + GitHub numa chamada."""
    anth = anth_client or _build_anthropic_client()
    return {
        "jira": await sync_jira_secrets(session, client, anth),
        "github": await sync_github_secrets(session, client, anth),
    }


async def delete_client_files(
    session: AsyncSession, client: Client,
    anth_client: anthropic.Anthropic | None = None,
) -> None:
    """Remove files do cliente (chamado em archive/delete do client).

    Limpa ambos file_ids e os arquivos remotos. Caller commita.
    """
    anth = anth_client or _build_anthropic_client()
    if client.jira_secrets_file_id:
        _safe_delete_file(anth, client.jira_secrets_file_id)
        client.jira_secrets_file_id = None
    if client.github_secrets_file_id:
        _safe_delete_file(anth, client.github_secrets_file_id)
        client.github_secrets_file_id = None
    await session.flush()
