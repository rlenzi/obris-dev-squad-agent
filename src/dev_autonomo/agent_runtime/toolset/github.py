"""Tools de integração GitHub: git_push + github_create_pr.

git_push: empurra a branch atual pro remote origin (que ja foi configurado
          com token pelo worktree manager).
github_create_pr: abre PR via GitHub API com o token do vault do client.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult
from dev_autonomo.common.credentials_store import (
    CredentialNotFoundError,
    get_secret,
)
from dev_autonomo.common.enums import SecretKind
from dev_autonomo.mcp_clients.github_client import GitHubClient


@dataclass
class GitPushTool:
    name: str = "git_push"
    description: str = (
        "Empurra a branch atual pro remote origin. Use depois de commit, "
        "antes de abrir PR."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "set_upstream": {
                    "type": "boolean",
                    "default": True,
                    "description": "Define a branch upstream (git push -u) na primeira vez.",
                },
            },
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if ctx.workspace_root is None:
            return ToolResult.error("workspace_root nao configurado", code="no_workspace")
        # Descobre branch atual
        rc, branch_out, err = await _run(ctx.workspace_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        if rc != 0:
            return ToolResult.error(f"git rev-parse falhou: {err}", code="git_error")
        branch = branch_out.strip()

        # --- Rebase automático sobre origin/<base_branch> antes do push ---
        # 1. Atualiza refs remotas
        rc, _, err = await _run(ctx.workspace_root, ["fetch", "origin"])
        if rc != 0:
            return ToolResult.error(f"git fetch origin falhou: {err.strip()}", code="git_error")

        # 2. Descobre a base branch (ctx.base_branch se disponível, senão "main")
        base_branch: str = getattr(ctx, "base_branch", None) or "main"

        # 3. Executa o rebase
        rc, _, rebase_err = await _run(ctx.workspace_root, ["rebase", f"origin/{base_branch}"])
        if rc != 0:
            # 4. Aborta o rebase para deixar o worktree limpo
            await _run(ctx.workspace_root, ["rebase", "--abort"])
            # Extrai arquivos em conflito do stderr (linhas "CONFLICT (...): ...")
            conflict_lines = [
                line for line in rebase_err.splitlines() if "CONFLICT" in line
            ]
            conflict_detail = "; ".join(conflict_lines) if conflict_lines else rebase_err.strip()
            return ToolResult.error(
                f"rebase em origin/{base_branch} falhou com conflito — {conflict_detail}",
                code="rebase_conflict",
            )
        # --- Fim do rebase ---

        args = ["push"]
        if inputs.get("set_upstream", True):
            args.append("-u")
        args.extend(["origin", branch])
        rc, out, err = await _run(ctx.workspace_root, args)
        if rc != 0:
            return ToolResult.error(
                f"git push falhou: {err.strip() or out.strip()}", code="git_error"
            )
        return ToolResult.ok({"pushed": True, "branch": branch})


@dataclass
class GitHubCreatePRTool:
    name: str = "github_create_pr"
    description: str = (
        "Abre um Pull Request no GitHub do cliente. Use depois de commit + push. "
        "Body deve descrever o que mudou, motivo, e como testar (1-3 paragrafos)."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Titulo conciso (max 72 chars). Ex: 'feat: add /payments idempotency'",
                },
                "body": {
                    "type": "string",
                    "description": "Descricao em markdown. Inclua: o que mudou, motivo, como testar, link pra task Jira.",
                },
                "base_branch": {
                    "type": "string",
                    "default": "main",
                    "description": "Branch alvo do merge (default 'main' ou o que estiver na squad).",
                },
                "draft": {
                    "type": "boolean",
                    "default": False,
                    "description": "Cria como draft se True.",
                },
            },
            "required": ["title", "body"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if ctx.workspace_root is None or not ctx.workspace_repo:
            return ToolResult.error(
                "workspace_root ou workspace_repo ausente", code="no_workspace"
            )

        # Descobre branch atual
        rc, branch_out, err = await _run(
            ctx.workspace_root, ["rev-parse", "--abbrev-ref", "HEAD"]
        )
        if rc != 0:
            return ToolResult.error(f"git rev-parse falhou: {err}", code="git_error")
        head_branch = branch_out.strip()

        # Extrai owner/repo do workspace_repo
        try:
            owner, repo_name = _extract_owner_repo(ctx.workspace_repo)
        except ValueError as exc:
            return ToolResult.error(f"URL invalido: {exc}", code="bad_repo_url")

        # Pega token GitHub do vault
        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()  # persiste last_used_at

        client = GitHubClient(token=token)
        try:
            pr = await client.create_pull_request(
                owner=owner,
                repo=repo_name,
                title=inputs["title"],
                head=head_branch,
                base=inputs.get("base_branch", "main"),
                body=inputs.get("body"),
                draft=bool(inputs.get("draft", False)),
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult.error(
                f"github API falhou: {exc}", code="github_error"
            )

        return ToolResult.ok(
            {
                "pr_number": pr.number,
                "pr_url": pr.html_url,
                "state": pr.state,
                "head": pr.head_ref,
                "base": pr.base_ref,
                "owner": owner,
                "repo": repo_name,
            }
        )


# ---- helpers ----


async def _run(cwd, args: list[str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


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
