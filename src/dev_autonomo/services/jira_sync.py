"""Sincronizacao bidirecional com Jira.

Funcoes:
- `post_stage_comment`: chamado pelos workflows quando uma task muda de
  estagio. Posta um comentario na issue Jira correspondente com texto
  derivado do template do estagio.
- `record_inbound_event`: chamado pelo `POST /webhooks/jira` quando um
  evento externo chega (comentario humano, transition). Apende ao
  `scan_progress.jira_events` na Task.

Status mapping (TaskStage -> Jira target status) eh estatico por enquanto
em `DEFAULT_STAGE_TO_JIRA_STATUS`. Edicao customizada por client fica
como TODO (precisa migration pra adicionar `client.jira_status_mapping`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.encryption import SecretEncryptor
from dev_autonomo.common.enums import SecretKind, TaskStage
from dev_autonomo.db.models import Client, EncryptedSecret, Task
from dev_autonomo.mcp_clients.jira_client import JiraClient

logger = logging.getLogger(__name__)


# Mapping default usado quando o cliente nao customizou. Stages
# intermediarios (sem entry) nao disparam transition — apenas comentario.
DEFAULT_STAGE_TO_JIRA_STATUS: dict[TaskStage, str] = {
    TaskStage.BA_REFINING: "In Progress",
    TaskStage.ARCHITECT_PLANNING: "In Progress",
    TaskStage.DEV_EXECUTING: "In Progress",
    TaskStage.PR_OPENED: "In Review",
    TaskStage.MERGED: "Done",
    TaskStage.CANCELLED: "Cancelled",
    TaskStage.FAILED: "Cancelled",
}


# Prosa default postada como comentario no Jira quando a task entra no
# estagio. Usar primeira pessoa (voz do sistema).
DEFAULT_STAGE_MESSAGES: dict[TaskStage, str] = {
    TaskStage.BA_REFINING: (
        "Pegamos a demanda — o BA vai refinar agora pra deixar a spec "
        "estruturada antes do plano técnico."
    ),
    TaskStage.ARCHITECT_PLANNING: (
        "Spec refinada. O Architect está montando o plano de execução."
    ),
    TaskStage.DEV_EXECUTING: (
        "Plano aprovado. Dev começou a implementar."
    ),
    TaskStage.PR_OPENED: (
        "PR aberto e aguardando revisão humana. Link no painel."
    ),
    TaskStage.MERGED: (
        "PR mergeado, demanda concluída."
    ),
    TaskStage.CANCELLED: (
        "Task cancelada antes do fim do pipeline."
    ),
    TaskStage.FAILED: (
        "Task falhou — pipeline pausado. Verifique no painel."
    ),
}


async def _load_jira_client(
    session: AsyncSession, client_id: UUID
) -> JiraClient | None:
    """Carrega credencial Jira do client e retorna um JiraClient.

    Retorna None se o cliente nao configurou Jira (estado valido — ele
    pode estar usando o /demands embutido).
    """
    client = await session.get(Client, client_id)
    if client is None:
        return None
    if not (client.jira_workspace_url and client.jira_email and client.jira_credential_id):
        return None

    cred = await session.get(EncryptedSecret, client.jira_credential_id)
    if cred is None or cred.kind != SecretKind.JIRA_TOKEN:
        logger.warning(
            "client %s tem jira_credential_id %s mas secret nao foi encontrada",
            client_id, client.jira_credential_id,
        )
        return None

    api_token = SecretEncryptor().decrypt(cred.encrypted_value)
    return JiraClient(
        base_url=client.jira_workspace_url,
        email=client.jira_email,
        api_token=api_token,
    )


async def post_stage_comment(
    session: AsyncSession,
    task: Task,
    stage: TaskStage,
    *,
    extra_message: str | None = None,
    transition: bool = True,
) -> bool:
    """Posta comentario no Jira sinalizando entrada em novo estagio.

    Se `transition` e o stage tem mapping em `DEFAULT_STAGE_TO_JIRA_STATUS`,
    tambem tenta transitar a issue pro status mapeado.

    Retorna True se conseguiu postar, False se cliente nao tem Jira
    configurado (sem erro — eh estado valido).
    """
    if not task.jira_issue_key:
        return False

    client = await _load_jira_client(session, task.client_id)
    if client is None:
        return False

    message = DEFAULT_STAGE_MESSAGES.get(stage, f"Entrei no estágio: {stage.value}")
    if extra_message:
        message = f"{message}\n\n{extra_message}"

    try:
        await client.add_comment(task.jira_issue_key, message)
    except Exception:
        logger.exception(
            "falha postando comment jira issue=%s stage=%s",
            task.jira_issue_key, stage.value,
        )
        return False

    if transition:
        target = DEFAULT_STAGE_TO_JIRA_STATUS.get(stage)
        if target:
            try:
                done = await client.transition_to_status(task.jira_issue_key, target)
                if done is None:
                    logger.info(
                        "nenhuma transition disponivel pra status=%s issue=%s",
                        target, task.jira_issue_key,
                    )
            except Exception:
                logger.exception(
                    "falha em transition jira issue=%s target=%s",
                    task.jira_issue_key, target,
                )

    return True


async def record_inbound_event(
    session: AsyncSession,
    task: Task,
    *,
    kind: str,
    author: str,
    body: str,
    raw: dict[str, Any] | None = None,
) -> None:
    """Apende evento externo na timeline da Task.

    Usa `scan_progress.jira_events: list[{ts, kind, author, body}]`. Caso
    `scan_progress` esteja None, inicializa.
    """
    progress = dict(task.scan_progress or {})
    events: list[dict[str, Any]] = list(progress.get("jira_events", []))
    events.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "author": author,
        "body": body[:2000],  # cap pra evitar payloads grandes
    })
    progress["jira_events"] = events[-50:]  # mantem ultimos 50
    task.scan_progress = progress
    await session.flush()


async def find_task_by_jira_key(
    session: AsyncSession, *, workspace_url: str, issue_key: str
) -> Task | None:
    """Resolve a Task local correspondente a uma issue Jira externa."""
    stmt = select(Task).where(
        Task.jira_workspace_url == workspace_url.rstrip("/"),
        Task.jira_issue_key == issue_key,
    )
    return (await session.execute(stmt)).scalar_one_or_none()
