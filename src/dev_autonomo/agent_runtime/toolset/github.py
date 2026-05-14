"""Tools de integração GitHub: git_push + github_create_pr + github_get_pr + github_review_pr + github_merge_pr.

git_push: empurra a branch atual pro remote origin (que ja foi configurado
          com token pelo worktree manager).
github_create_pr: abre PR via GitHub API com o token do vault do client.
github_get_pr: lê metadados + lista de arquivos de um PR existente.
github_review_pr: submete uma review (APPROVE / REQUEST_CHANGES / COMMENT) num PR existente.
github_merge_pr: faz merge de um PR — desabilitado por default via ctx.enable_auto_merge.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

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
        "Body deve descrever o que mudou, motivo, e como testar (1-3 paragrafos). "
        "ATENCAO: a tool valida que a branch ja foi pushada — recusa criar PR se "
        "branch local nao existe no remote ou tem commits unpushed."
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

        rc, branch_out, err = await _run(
            ctx.workspace_root, ["rev-parse", "--abbrev-ref", "HEAD"]
        )
        if rc != 0:
            return ToolResult.error(f"git rev-parse falhou: {err}", code="git_error")
        head_branch = branch_out.strip()

        # LEO-39: defesa contra Dev pular o git_push e ir direto pro create_pr.
        # Antes de criar o PR, garante que a branch existe no remote e não tem
        # commits locais pendentes.
        await _run(ctx.workspace_root, ["fetch", "origin"])
        rc_v, _, _ = await _run(
            ctx.workspace_root, ["rev-parse", "--verify", f"origin/{head_branch}"]
        )
        if rc_v != 0:
            return ToolResult.error(
                f"branch '{head_branch}' nao existe no remote. "
                f"Execute git_push antes de chamar github_create_pr.",
                code="branch_not_pushed",
            )
        rc_c, count_out, _ = await _run(
            ctx.workspace_root,
            ["rev-list", "--count", f"origin/{head_branch}..HEAD"],
        )
        if rc_c == 0:
            try:
                ahead = int(count_out.strip())
            except ValueError:
                ahead = 0
            if ahead > 0:
                return ToolResult.error(
                    f"branch local tem {ahead} commit(s) ainda nao pushado(s). "
                    f"Execute git_push antes de chamar github_create_pr.",
                    code="unpushed_commits",
                )

        try:
            owner, repo_name = _extract_owner_repo(ctx.workspace_repo)
        except ValueError as exc:
            return ToolResult.error(f"URL invalido: {exc}", code="bad_repo_url")

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

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
        except Exception as exc:
            return ToolResult.error(
                f"github API falhou: {exc}", code="github_error"
            )

        # Persiste a URL do PR na Task pra link direto no admin/cliente.
        # Sem isso, painel só consegue mostrar busca "/pulls?q=is:pr+LEO-N".
        if ctx.task_id is not None:
            from dev_autonomo.db.models.task import Task as _Task

            task = (
                await ctx.session.execute(
                    select(_Task).where(_Task.id == ctx.task_id)
                )
            ).scalar_one_or_none()
            if task is not None:
                task.pr_url = pr.html_url
                await ctx.session.commit()

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


@dataclass
class GitHubGetPRTool:
    name: str = "github_get_pr"
    description: str = (
        "Lê metadados e lista de arquivos alterados de um Pull Request existente. "
        "Retorna title, body, state, draft, head_ref, base_ref, mergeable, "
        "additions, deletions, changed_files e a lista de arquivos com patch "
        "truncado em 8 KB por arquivo."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "Número do Pull Request a consultar.",
                },
            },
            "required": ["pr_number"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if not ctx.workspace_repo:
            return ToolResult.error(
                "workspace_repo ausente no contexto", code="no_workspace"
            )

        try:
            owner, repo_name = _extract_owner_repo(ctx.workspace_repo)
        except ValueError as exc:
            return ToolResult.error(f"URL invalido: {exc}", code="bad_repo_url")

        authz = await ctx.enforcer.check_repo(ctx.workspace_repo)
        if not authz.allowed:
            return ToolResult.error(
                authz.suggestion or "repo nao autorizado pelo manifest",
                code=authz.reason,
            )

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

        pr_number: int = int(inputs["pr_number"])
        client = GitHubClient(token=token)
        try:
            pr_data = await client.get_pull_request(owner, repo_name, pr_number)
            files = await client.list_pull_request_files(owner, repo_name, pr_number)
        except Exception as exc:
            return ToolResult.error(
                f"github API falhou: {exc}", code="github_error"
            )

        return ToolResult.ok(
            {
                "pr_number": pr_number,
                "owner": owner,
                "repo": repo_name,
                **pr_data,
                "files": files,
            }
        )


@dataclass
class GitHubGetPRChecksTool:
    """Lê o status agregado dos checks do CI no PR.

    O Reviewer usa essa tool ANTES de aprovar — se o CI está failing,
    bloqueia (REQUEST_CHANGES). Combina GitHub Actions check-runs + legacy
    status API.
    """

    name: str = "github_get_pr_checks"
    description: str = (
        "Le o status dos checks do CI (GitHub Actions) num PR. Retorna estado "
        "agregado (success/failure/pending/neutral) + lista de checks com "
        "nome, status, conclusao e URL. Use ANTES de aprovar uma review — "
        "se CI esta falhando, peca REQUEST_CHANGES."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "Numero do PR a consultar.",
                },
            },
            "required": ["pr_number"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if not ctx.workspace_repo:
            return ToolResult.error(
                "workspace_repo ausente no contexto", code="no_workspace"
            )

        try:
            owner, repo_name = _extract_owner_repo(ctx.workspace_repo)
        except ValueError as exc:
            return ToolResult.error(f"URL invalido: {exc}", code="bad_repo_url")

        authz = await ctx.enforcer.check_repo(ctx.workspace_repo)
        if not authz.allowed:
            return ToolResult.error(
                authz.suggestion or "repo nao autorizado pelo manifest",
                code=authz.reason,
            )

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

        pr_number: int = int(inputs["pr_number"])
        client = GitHubClient(token=token)
        try:
            data = await client.get_pull_request_checks(owner, repo_name, pr_number)
        except Exception as exc:
            return ToolResult.error(
                f"github API falhou: {exc}", code="github_error"
            )

        return ToolResult.ok(
            {
                "pr_number": pr_number,
                **data,
            }
        )


@dataclass
class GitHubGetReviewCommentsTool:
    """Le a ultima review e os comentarios inline de um PR.

    Usado pelo Dev quando reage a um REQUEST_CHANGES do Reviewer: precisa
    ler exatamente o que o Reviewer pediu (general + inline comments com
    path+linha) pra produzir o fix.
    """

    name: str = "github_get_review_comments"
    description: str = (
        "Le as reviews submetidas e os comentarios inline (com path+linha) "
        "num PR. Use ANTES de fazer fix em resposta a REQUEST_CHANGES — voce "
        "precisa saber exatamente o que o Reviewer pediu antes de mexer no "
        "codigo. Retorna lista de reviews (com state APPROVE/REQUEST_CHANGES/"
        "COMMENT + body geral) e lista de comentarios inline (path, line, "
        "body, user_login)."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "Numero do PR a consultar.",
                },
                "only_latest_request_changes": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Se True (default), retorna apenas a review mais "
                        "recente do tipo REQUEST_CHANGES (e seus inline "
                        "comments). Se False, retorna tudo."
                    ),
                },
            },
            "required": ["pr_number"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if not ctx.workspace_repo:
            return ToolResult.error(
                "workspace_repo ausente no contexto", code="no_workspace"
            )

        try:
            owner, repo_name = _extract_owner_repo(ctx.workspace_repo)
        except ValueError as exc:
            return ToolResult.error(f"URL invalido: {exc}", code="bad_repo_url")

        authz = await ctx.enforcer.check_repo(ctx.workspace_repo)
        if not authz.allowed:
            return ToolResult.error(
                authz.suggestion or "repo nao autorizado pelo manifest",
                code=authz.reason,
            )

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

        pr_number: int = int(inputs["pr_number"])
        only_latest = bool(inputs.get("only_latest_request_changes", True))
        client = GitHubClient(token=token)

        try:
            reviews = await client.list_pull_request_reviews(
                owner, repo_name, pr_number
            )
            inline = await client.list_pull_request_review_comments(
                owner, repo_name, pr_number
            )
        except Exception as exc:
            return ToolResult.error(
                f"github API falhou: {exc}", code="github_error"
            )

        latest_request: dict[str, Any] | None = None
        if reviews:
            for rev in reversed(reviews):
                if rev.get("state") == "CHANGES_REQUESTED":
                    latest_request = rev
                    break

        result: dict[str, Any] = {
            "pr_number": pr_number,
            "latest_request_changes": latest_request,
        }

        if only_latest and latest_request is not None:
            related = [
                c
                for c in inline
                if (c.get("user_login") == latest_request.get("user_login"))
            ]
            result["inline_comments"] = related
            result["inline_comments_count"] = len(related)
        else:
            result["reviews"] = reviews
            result["inline_comments"] = inline
            result["inline_comments_count"] = len(inline)

        return ToolResult.ok(result)


_DECISION_TO_EVENT: dict[str, str] = {
    "approve": "APPROVE",
    "request_changes": "REQUEST_CHANGES",
    "comment": "COMMENT",
}


@dataclass
class GitHubReviewPRTool:
    name: str = "github_review_pr"
    description: str = (
        "Submete uma review num Pull Request do GitHub do cliente. "
        "Use para aprovar, pedir mudancas ou comentar em um PR existente. "
        "Passa pelo enforcer.check_repo antes de agir."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "Numero do Pull Request a ser revisado.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["approve", "request_changes", "comment"],
                    "description": (
                        "Decisao da review: "
                        "'approve' (aprova o PR), "
                        "'request_changes' (pede alteracoes), "
                        "'comment' (apenas comenta sem aprovar nem bloquear)."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": "Comentario geral da review (obrigatorio).",
                },
                "inline_comments": {
                    "type": "array",
                    "description": (
                        "Lista opcional de comentarios inline no diff. "
                        "Cada item deve conter: 'path' (caminho do arquivo), "
                        "'position' ou 'line' (posicao no diff), e 'body' (texto)."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["pr_number", "decision", "body"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if ctx.workspace_repo is None:
            return ToolResult.error(
                "workspace_repo nao configurado no contexto", code="no_workspace"
            )

        auth = await ctx.enforcer.check_repo(ctx.workspace_repo)
        await ctx.enforcer.authorize(self.name, ctx.workspace_repo, auth)
        if not auth.allowed:
            return ToolResult.error(
                auth.suggestion or "repo bloqueado pelo manifest",
                code=auth.reason,
            )

        decision = str(inputs.get("decision", "")).lower()
        event = _DECISION_TO_EVENT.get(decision)
        if event is None:
            return ToolResult.error(
                f"decision invalida: '{decision}'. Use 'approve', 'request_changes' ou 'comment'.",
                code="bad_input",
            )

        try:
            owner, repo_name = _extract_owner_repo(ctx.workspace_repo)
        except ValueError as exc:
            return ToolResult.error(f"URL invalido: {exc}", code="bad_repo_url")

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

        client = GitHubClient(token=token)
        try:
            data = await client.create_pull_request_review(
                owner=owner,
                repo=repo_name,
                number=int(inputs["pr_number"]),
                event=event,
                body=inputs["body"],
                comments=inputs.get("inline_comments") or None,
            )
        except ValueError as exc:
            return ToolResult.error(str(exc), code="bad_input")
        except Exception as exc:
            return ToolResult.error(
                f"github API falhou: {exc}", code="github_error"
            )

        return ToolResult.ok(
            {
                "review_id": data.get("id"),
                "pr_number": inputs["pr_number"],
                "state": data.get("state"),
                "decision": decision,
                "event": event,
                "html_url": data.get("html_url"),
                "owner": owner,
                "repo": repo_name,
            }
        )


@dataclass
class GitHubMergePRTool:
    """Faz merge de um Pull Request no GitHub.

    Desabilitada por default via ctx.enable_auto_merge (False).
    Passa por enforcer.check_repo antes de qualquer chamada de rede.
    """

    name: str = "github_merge_pr"
    description: str = (
        "Faz merge de um Pull Request no GitHub do cliente. "
        "Requer enable_auto_merge=True no contexto de execução; "
        "caso contrário retorna erro 'auto-merge desabilitado nesta versao'."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "pr_number": {
                    "type": "integer",
                    "description": "Número do Pull Request a ser mergeado.",
                },
                "merge_method": {
                    "type": "string",
                    "enum": ["squash", "merge", "rebase"],
                    "default": "squash",
                    "description": "Estratégia de merge. Default: 'squash'.",
                },
                "commit_title": {
                    "type": "string",
                    "description": "Título opcional do commit de merge.",
                },
            },
            "required": ["pr_number"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if not getattr(ctx, "enable_auto_merge", False):
            return ToolResult.error(
                "auto-merge desabilitado nesta versao",
                code="auto_merge_disabled",
            )

        if not ctx.workspace_repo:
            return ToolResult.error(
                "workspace_repo ausente no contexto", code="no_workspace"
            )

        auth = await ctx.enforcer.check_repo(ctx.workspace_repo)
        if not auth.allowed:
            return ToolResult.error(
                auth.suggestion or "repo fora do escopo da squad",
                code=auth.reason,
            )

        try:
            owner, repo_name = _extract_owner_repo(ctx.workspace_repo)
        except ValueError as exc:
            return ToolResult.error(f"URL invalido: {exc}", code="bad_repo_url")

        try:
            token = await get_secret(
                ctx.session,
                client_id=ctx.client_id,
                kind=SecretKind.GITHUB_TOKEN,
            )
        except CredentialNotFoundError as exc:
            return ToolResult.error(str(exc), code="credential_missing")

        await ctx.session.commit()

        pr_number: int = int(inputs["pr_number"])
        merge_method: str = inputs.get("merge_method", "squash")
        commit_title: str | None = inputs.get("commit_title")

        client = GitHubClient(token=token)
        try:
            result = await client.merge_pull_request(
                owner=owner,
                repo=repo_name,
                number=pr_number,
                merge_method=merge_method,
                commit_title=commit_title,
            )
        except Exception as exc:
            return ToolResult.error(
                f"github API falhou: {exc}", code="github_error"
            )

        return ToolResult.ok(
            {
                "merged": result.get("merged", True),
                "sha": result.get("sha"),
                "message": result.get("message"),
                "pr_number": pr_number,
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
