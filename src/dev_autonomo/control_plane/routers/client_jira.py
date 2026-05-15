"""Router /client/jira: configuracao da integracao Jira do tenant.

GET /client/jira/integration -> info read-only com:
- webhook URL (publica, pro cliente configurar na Jira Cloud)
- status mapping default (stage -> status)
- estado da credencial (conectado / nao conectado)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from dev_autonomo.common.enums import UserRole
from dev_autonomo.control_plane.dependencies import require_client_context
from dev_autonomo.db.models import Client
from dev_autonomo.services.jira_sync import (
    DEFAULT_STAGE_MESSAGES,
    DEFAULT_STAGE_TO_JIRA_STATUS,
)

router = APIRouter(prefix="/client/jira", tags=["client / jira"])


@router.get("/integration")
async def get_jira_integration(
    request: Request,
    ctx: tuple[Client, UserRole] = Depends(require_client_context),
) -> dict[str, Any]:
    client, _ = ctx

    # Webhook URL absoluta — usa Request.url pra montar baseada na host atual.
    # Em produção, sera https://api.dev-autonomo.com/webhooks/jira. Em dev,
    # localhost. Cliente cola essa URL no Jira Cloud (Settings -> System ->
    # Webhooks).
    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/webhooks/jira"

    stage_mapping = [
        {
            "stage": stage.value,
            "target_status": target,
            "message_preview": DEFAULT_STAGE_MESSAGES.get(stage, ""),
        }
        for stage, target in DEFAULT_STAGE_TO_JIRA_STATUS.items()
    ]

    return {
        "connected": bool(
            client.jira_workspace_url
            and client.jira_email
            and client.jira_credential_id
        ),
        "workspace_url": client.jira_workspace_url,
        "email": client.jira_email,
        "webhook_url": webhook_url,
        "stage_mapping": stage_mapping,
        "supported_events": ["comment_created", "jira:issue_updated"],
    }
