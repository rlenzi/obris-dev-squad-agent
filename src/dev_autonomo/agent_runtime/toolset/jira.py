"""Tools de Jira: get_issue, update_status, add_comment, create_subtask.

Todas passam pelo ManifestEnforcer.check_jira_project antes de qualquer mudanca
no Jira. O token Jira vem do vault do cliente (encrypted_secrets).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult
from dev_autonomo.common.credentials_store import (
    CredentialNotFoundError,
    get_secret,
)
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.db.models import Client
from dev_autonomo.mcp_clients.jira_client import JiraClient


async def _build_client(ctx: AgentRunContext) -> JiraClient | ToolResult:
    """Constroi um JiraClient autenticado pra o client_id do contexto."""
    client_row = await ctx.session.get(Client, ctx.client_id)
    if client_row is None or not client_row.jira_workspace_url or not client_row.jira_email:
        return ToolResult.error(
            "cliente nao tem jira_workspace_url ou jira_email configurados",
            code="jira_not_configured",
        )
    try:
        token = await get_secret(
            ctx.session, client_id=ctx.client_id, kind=SecretKind.JIRA_TOKEN
        )
    except CredentialNotFoundError as exc:
        return ToolResult.error(str(exc), code="credential_missing")
    await ctx.session.commit()
    return JiraClient(
        base_url=client_row.jira_workspace_url,
        email=client_row.jira_email,
        api_token=token,
    )


def _project_from_key(issue_key: str) -> str:
    """Extrai project key de uma issue key (ex: LEO-42 -> LEO)."""
    return issue_key.split("-", 1)[0]


async def _enforce_project(
    ctx: AgentRunContext, tool_name: str, issue_key: str
) -> ToolResult | None:
    project = _project_from_key(issue_key)
    result = await ctx.enforcer.check_jira_project(project)
    await ctx.enforcer.authorize(tool_name, f"jira:{issue_key}", result)
    if not result.allowed:
        return ToolResult.error(
            result.suggestion or f"projeto Jira '{project}' fora do escopo da squad",
            code=result.reason,
        )
    return None


@dataclass
class JiraGetIssueTool:
    name: str = "jira_get_issue"
    description: str = (
        "Le uma issue do Jira do cliente: summary, status, descricao, type, assignee. "
        "Use no inicio da task pra entender o que esta sendo pedido."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Issue key no formato 'PROJ-N' (ex: 'LEO-42').",
                },
            },
            "required": ["issue_key"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        key = inputs["issue_key"]
        blocked = await _enforce_project(ctx, self.name, key)
        if blocked is not None:
            return blocked
        client = await _build_client(ctx)
        if isinstance(client, ToolResult):
            return client
        try:
            issue = await client.get_issue(key)
        except Exception as exc:
            return ToolResult.error(f"jira get_issue falhou: {exc}", code="jira_error")
        return ToolResult.ok(
            {
                "key": issue.key,
                "summary": issue.summary,
                "status": issue.status,
                "issue_type": issue.issue_type,
                "description": issue.description_text,
                "assignee": issue.assignee,
            }
        )


@dataclass
class JiraUpdateStatusTool:
    name: str = "jira_update_status"
    description: str = (
        "Transiciona uma issue do Jira para outro status (ex: 'In Progress', 'Done'). "
        "O sistema busca a transition disponivel cujo target ou nome bate com o "
        "valor passado."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string"},
                "target_status": {
                    "type": "string",
                    "description": "Status alvo (ex: 'In Progress', 'Done', 'In Review').",
                },
            },
            "required": ["issue_key", "target_status"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        key = inputs["issue_key"]
        target = inputs["target_status"]
        blocked = await _enforce_project(ctx, self.name, key)
        if blocked is not None:
            return blocked
        client = await _build_client(ctx)
        if isinstance(client, ToolResult):
            return client
        try:
            executed = await client.transition_to_status(key, target)
        except Exception as exc:
            return ToolResult.error(
                f"jira transition falhou: {exc}", code="jira_error"
            )
        if executed is None:
            # Lista alternativas para o agente saber o que e valido
            try:
                transitions = await client.list_transitions(key)
                options = [t.name for t in transitions]
            except Exception:
                options = []
            return ToolResult.error(
                f"nenhuma transition bate com '{target}'. Opcoes: {options}",
                code="invalid_transition",
            )
        return ToolResult.ok(
            {"issue_key": key, "transitioned": True, "transition_used": executed}
        )


@dataclass
class JiraAddCommentTool:
    name: str = "jira_add_comment"
    description: str = (
        "Adiciona um comentario em uma issue do Jira. Use pra reportar progresso, "
        "anexar link do PR, justificar decisoes, etc."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "issue_key": {"type": "string"},
                "comment": {
                    "type": "string",
                    "description": "Texto do comentario (markdown simples; quebras de linha duplas viram paragrafos).",
                },
            },
            "required": ["issue_key", "comment"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        key = inputs["issue_key"]
        comment_text = inputs["comment"]
        blocked = await _enforce_project(ctx, self.name, key)
        if blocked is not None:
            return blocked
        client = await _build_client(ctx)
        if isinstance(client, ToolResult):
            return client
        try:
            comment = await client.add_comment(key, comment_text)
        except Exception as exc:
            return ToolResult.error(
                f"jira add_comment falhou: {exc}", code="jira_error"
            )
        return ToolResult.ok({"issue_key": key, "comment_id": comment.id})


@dataclass
class JiraCreateSubtaskTool:
    name: str = "jira_create_subtask"
    description: str = (
        "Cria uma sub-task linkada a uma issue parent. Usado tipicamente pelo "
        "Architect Agent ao decompor uma demanda em N sub-tasks pros Devs."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "parent_key": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["parent_key", "summary"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        parent = inputs["parent_key"]
        summary = inputs["summary"]
        blocked = await _enforce_project(ctx, self.name, parent)
        if blocked is not None:
            return blocked
        client = await _build_client(ctx)
        if isinstance(client, ToolResult):
            return client
        project = _project_from_key(parent)
        try:
            issue = await client.create_subtask(
                parent_key=parent,
                project_key=project,
                summary=summary,
                description_text=inputs.get("description"),
            )
        except Exception as exc:
            return ToolResult.error(
                f"jira create_subtask falhou: {exc}", code="jira_error"
            )
        return ToolResult.ok(
            {
                "subtask_key": issue.key,
                "parent_key": parent,
                "summary": issue.summary,
            }
        )
