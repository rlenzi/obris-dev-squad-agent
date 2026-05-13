"""Receivers de webhooks externos (GitHub, futuramente outros).

FastAPI app minimal. NAO eh o Control Plane completo (fase 2.1) — apenas
o ponto de entrada de eventos que precisam aterrissar em queues do RabbitMQ.

Roteamento:
- POST /webhooks/github
    Header X-GitHub-Event determina o tipo:
      * `push` para refs/heads/main -> extrai diff e publica ReindexMessage
        em REINDEX_QUEUE (devauto.knowledge.reindex).
      * `pull_request_review_comment` -> enfileira em QUEUE_PLAYBOOK_MINER
    Outros tipos: ignorados (200 OK silencioso para evitar retry do GitHub).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.queue import (
    QUEUE_PLAYBOOK_MINER,
    publish,
)
from dev_autonomo.common.repos import normalize_repo_id
from dev_autonomo.db.models import Manifest, Squad
from dev_autonomo.db.session import get_session
from dev_autonomo.knowledge.reindex_schema import REINDEX_QUEUE, ReindexMessage

app = FastAPI(title="dev-autonomo webhooks", version="0.1.0")
logger = logging.getLogger(__name__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _verify_signature(body: bytes, signature_header: str | None, secret: str | None) -> bool:
    """Verifica X-Hub-Signature-256 contra body. Sem secret = aceita (modo dev)."""
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    received = signature_header.split("=", 1)[1]
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


async def _resolve_squad_for_repo(
    session: AsyncSession, repo_full_name: str
) -> tuple[UUID, UUID] | None:
    """Procura a squad cujo manifest tem esse repo no owns.repos.

    Retorna (client_id, squad_id) ou None se nenhuma squad reivindica o repo.
    """
    repo_norm = normalize_repo_id(repo_full_name)

    stmt = (
        select(Squad.client_id, Squad.id, Manifest.content)
        .join(Manifest, Squad.current_manifest_id == Manifest.id)
    )
    result = await session.execute(stmt)
    for client_id, squad_id, content in result.all():
        repos = (content or {}).get("owns", {}).get("repos", [])
        if any(normalize_repo_id(r) == repo_norm for r in repos):
            return client_id, squad_id
    return None


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
) -> dict[str, Any]:
    body = await request.body()

    # Em produção, um secret por client_id seria carregado do banco.
    # Por enquanto, modo dev sem verificacao (sem secret configurado).
    if not _verify_signature(body, x_hub_signature_256, secret=None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    import json
    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid JSON")

    event = (x_github_event or "").lower()
    repo_full_name: str = (payload.get("repository") or {}).get("full_name", "")
    if not repo_full_name:
        return {"status": "ignored", "reason": "no repository in payload"}

    # Tenta resolver squad pelo repo
    async for session in get_session():
        squad_resolution = await _resolve_squad_for_repo(session, repo_full_name)
        break  # pegamos so o primeiro yield

    if squad_resolution is None:
        logger.info(
            "Webhook ignorado: repo %s nao pertence a nenhuma squad com manifest ativo",
            repo_full_name,
        )
        return {"status": "ignored", "reason": "no squad owns this repo"}

    client_id, squad_id = squad_resolution

    if event == "push":
        ref: str = payload.get("ref", "")

        # Filtra apenas pushes para a branch principal
        if ref != "refs/heads/main":
            logger.debug("Push ignorado: ref=%s nao eh refs/heads/main", ref)
            return {"status": "ignored", "reason": f"ref '{ref}' nao eh refs/heads/main"}

        # Extrai arquivos afetados de todos os commits (added + modified + removed)
        affected: set[str] = set()
        for commit in payload.get("commits", []):
            affected.update(commit.get("added", []) or [])
            affected.update(commit.get("modified", []) or [])
            affected.update(commit.get("removed", []) or [])

        files: list[str] = sorted(affected)

        # Push sem arquivos relevantes — retorna sem publicar na fila
        if not files:
            logger.info(
                "Push ignorado: nenhum arquivo afetado em %s ref=%s",
                repo_full_name,
                ref,
            )
            return {"status": "ignored", "reason": "no_files"}

        msg = ReindexMessage(
            client_id=client_id,
            squad_id=squad_id,
            repo=repo_full_name,
            ref=ref,
            commit_hash=payload.get("after", ""),
            files=files,
        )
        await publish(REINDEX_QUEUE, msg.to_dict())

        logger.info(
            "Push enfileirado para reindex: repo=%s ref=%s files=%d commit=%s",
            repo_full_name,
            ref,
            len(files),
            msg.commit_hash,
        )
        return {"status": "queued", "files": len(files)}

    if event == "pull_request_review_comment":
        comment = payload.get("comment") or {}
        pr_data = payload.get("pull_request") or {}
        await publish(
            QUEUE_PLAYBOOK_MINER,
            {
                "client_id": str(client_id),
                "squad_id": str(squad_id),
                "pr_number": pr_data.get("number"),
                "comment_id": comment.get("id"),
                "comment_body": comment.get("body", ""),
                "file_path": comment.get("path"),
                "diff_hunk": comment.get("diff_hunk"),
                "author_login": (comment.get("user") or {}).get("login"),
            },
        )
        return {"status": "queued", "queue": QUEUE_PLAYBOOK_MINER}

    return {"status": "ignored", "reason": f"event '{event}' nao suportado"}
