"""Tools do Reviewer Agent: github_get_pr + github_review_pr.

github_get_pr:    Le um PR aberto via GitHub API (titulo, body, diff, arquivos).
github_review_pr: Submete um review (APPROVE ou REQUEST_CHANGES) com body PT-BR.

Sem merge automatico — review only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult
from dev_autonomo.common.credentials_store import (
    CredentialNotFoundError,
    get_secret,
)
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.mcp_clients.github_client import GitHubClient

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0

# Limite maximo de bytes para o diff (evita contexto gigante pro LLM)
_MAX_DIFF_BYTES = 48_000


@dataclass
class GitHubGetPRTool:
    """Le um Pull Request aberto: metadata, body, lista de arquivos e diff truncado."""

    name: str = "github_get_pr"
    description: str = (
        "Le um Pull Request aberto no GitHub do cliente. Retorna titulo, body, "
        "branch, lista de arquivos alterados e diff (truncado a 48 KB). "
        "Use antes de github_review_pr para entender o que esta sendo revisado."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "Numero do Pull Request (ex: 42).",
                },
                "repo_url": {
                    "type": "string",
                    "description": (
                        "URL do repositorio GitHub (ex: "
                        "'https://github.com/org/repo'). "
                        "Se omitido, usa o workspace_repo do contexto."
                    ),
                },
            },
            "required": ["pr_number"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        pr_number: int = int(inputs["pr_number"])
        repo_url: str | None = inputs.get("repo_url") or ctx.workspace_repo
        if not repo_url:
            return ToolResult.error(
                "repo_url nao informado e workspace_repo ausente no contexto",
                code="missing_repo",
            )

        try:
            owner, repo_name = _extract_owner_repo(repo_url)
        except ValueError as exc:
            return ToolResult.error(f"URL de repo invalido: {exc}", code="bad_repo_url")

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "obris-dev-squad-agent",
        }

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                # 1. Metadados do PR
                pr_resp = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo_name}/pulls/{pr_number}",
                    headers=headers,
                )
                if pr_resp.status_code == 404:
                    return ToolResult.error(
                        f"PR #{pr_number} nao encontrado em {owner}/{repo_name}",
                        code="pr_not_found",
                    )
                pr_resp.raise_for_status()
                pr_data = pr_resp.json()

                # 2. Arquivos alterados
                files_resp = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo_name}/pulls/{pr_number}/files",
                    headers=headers,
                )
                files_resp.raise_for_status()
                files_data = files_resp.json()

                # 3. Diff raw (Accept diferente)
                diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
                diff_resp = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo_name}/pulls/{pr_number}",
                    headers=diff_headers,
                )
                diff_resp.raise_for_status()
                diff_raw = diff_resp.text[:_MAX_DIFF_BYTES]
                diff_truncated = len(diff_resp.text) > _MAX_DIFF_BYTES

        except httpx.HTTPStatusError as exc:
            return ToolResult.error(
                f"GitHub API erro {exc.response.status_code}: {exc.response.text[:300]}",
                code="github_error",
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult.error(f"Erro ao consultar GitHub: {exc}", code="github_error")

        files_summary = [
            {
                "filename": f["filename"],
                "status": f["status"],
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "changes": f.get("changes", 0),
            }
            for f in files_data
        ]

        return ToolResult.ok(
            {
                "pr_number": pr_data["number"],
                "title": pr_data["title"],
                "state": pr_data["state"],
                "html_url": pr_data["html_url"],
                "head_branch": pr_data["head"]["ref"],
                "base_branch": pr_data["base"]["ref"],
                "author": pr_data["user"]["login"],
                "body": pr_data.get("body") or "",
                "files": files_summary,
                "diff": diff_raw,
                "diff_truncated": diff_truncated,
                "owner": owner,
                "repo": repo_name,
            }
        )


@dataclass
class GitHubReviewPRTool:
    """Submete um review formal (APPROVE ou REQUEST_CHANGES) num PR do GitHub."""

    name: str = "github_review_pr"
    description: str = (
        "Submete um review num Pull Request do GitHub. "
        "Use decision='APPROVE' se o PR esta pronto pra merge, "
        "ou decision='REQUEST_CHANGES' se precisar de ajustes. "
        "O body deve ser escrito em PT-BR explicando a decisao. "
        "NAO faz merge — review only."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "Numero do Pull Request.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                    "description": (
                        "APPROVE: PR esta ok. "
                        "REQUEST_CHANGES: precisa de ajustes. "
                        "COMMENT: apenas comentario, sem bloquear."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": (
                        "Texto do review em PT-BR. Explique a decisao, "
                        "aponte problemas ou elogios especificos, referencie "
                        "arquivos quando relevante. Minimo 2 paragrafos."
                    ),
                },
                "repo_url": {
                    "type": "string",
                    "description": (
                        "URL do repositorio (ex: 'https://github.com/org/repo'). "
                        "Se omitido, usa workspace_repo do contexto."
                    ),
                },
            },
            "required": ["pr_number", "decision", "body"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        pr_number: int = int(inputs["pr_number"])
        decision: str = inputs["decision"].upper()
        body: str = inputs["body"]
        repo_url: str | None = inputs.get("repo_url") or ctx.workspace_repo

        if decision not in {"APPROVE", "REQUEST_CHANGES", "COMMENT"}:
            return ToolResult.error(
                f"decision invalida: '{decision}'. Use APPROVE, REQUEST_CHANGES ou COMMENT.",
                code="invalid_decision",
            )

        if not repo_url:
            return ToolResult.error(
                "repo_url nao informado e workspace_repo ausente no contexto",
                code="missing_repo",
            )

        try:
            owner, repo_name = _extract_owner_repo(repo_url)
        except ValueError as exc:
            return ToolResult.error(f"URL de repo invalido: {exc}", code="bad_repo_url")

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "obris-dev-squad-agent",
        }

        payload = {
            "body": body,
            "event": decision,
        }

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(
                    f"{GITHUB_API}/repos/{owner}/{repo_name}/pulls/{pr_number}/reviews",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 422:
                    # Ex: tentar aprovar o proprio PR, ou PR ja fechado
                    return ToolResult.error(
                        f"GitHub rejeitou o review: {resp.text[:300]}",
                        code="review_rejected",
                    )
                if resp.status_code >= 400:
                    return ToolResult.error(
                        f"GitHub API erro {resp.status_code}: {resp.text[:300]}",
                        code="github_error",
                    )
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return ToolResult.error(
                f"Erro ao submeter review: {exc}", code="github_error"
            )

        return ToolResult.ok(
            {
                "review_id": data.get("id"),
                "pr_number": pr_number,
                "decision": decision,
                "html_url": data.get("html_url", ""),
                "submitted_at": data.get("submitted_at", ""),
                "owner": owner,
                "repo": repo_name,
            }
        )


# ---- helpers ----


def _extract_owner_repo(repo_url: str) -> tuple[str, str]:
    s = repo_url.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    if s.startswith("git@"):
        path = s.split(":", 1)[1]
    else:
        parsed = urlparse(s)
        path = parsed.path.lstrip("/")
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"URL invalido: {repo_url}")
    return parts[-2], parts[-1]
