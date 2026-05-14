"""Tools básicas da Fase 3.1a: retrieve_knowledge, read_file, signal_complete."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult
from dev_autonomo.knowledge.qdrant_client import KnowledgePartition


@dataclass
class RetrieveKnowledgeTool:
    name: str = "retrieve_knowledge"
    description: str = (
        "Busca codigo e contexto relevante no Knowledge Hub da squad. Use para "
        "encontrar implementacoes existentes, padroes do codebase, e contexto "
        "antes de propor mudancas. Aplica boundary filter pelo manifesto: so "
        "retorna o que esta dentro do escopo da squad."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pergunta em linguagem natural (PT ou EN). Ex: 'how is user authentication implemented'",
                },
                "partition": {
                    "type": "string",
                    "enum": ["code", "playbook", "architecture", "conventions"],
                    "default": "code",
                    "description": "Partição do Knowledge Hub a buscar.",
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "kind_filter": {
                    "type": "string",
                    "enum": ["function", "class", "method", "type", "interface"],
                    "description": "Filtra por tipo de chunk (opcional).",
                },
            },
            "required": ["query"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        query: str = inputs["query"]
        partition_str = inputs.get("partition", "code")
        try:
            partition = KnowledgePartition(partition_str)
        except ValueError:
            return ToolResult.error(
                f"partition invalida: {partition_str}", code="invalid_input"
            )
        limit = int(inputs.get("limit", 5))
        kind_filter = inputs.get("kind_filter")

        result = await ctx.retriever.retrieve(
            squad_id=ctx.squad_id,
            query=query,
            partition=partition,
            limit=limit,
            kind_filter=kind_filter,
            strict_manifest=True,
        )

        hits_compact = [
            {
                "score": round(hit.score, 3),
                "kind": hit.kind,
                "name": hit.name,
                "parent": hit.parent,
                "file": hit.file_path,
                "lines": f"{hit.start_line}-{hit.end_line}",
                "repo": hit.repo,
                "language": hit.language,
                "signature": hit.signature,
                # truncamos preview do conteudo
                "content_preview": hit.content[:800] if hit.content else "",
            }
            for hit in result.hits
        ]
        return ToolResult.ok(
            {
                "query": query,
                "partition": partition.value,
                "hits": hits_compact,
                "filtered_by_manifest": result.filtered_by_manifest,
                "discarded_out_of_scope": result.discarded_out_of_scope,
            }
        )


@dataclass
class ReadFileTool:
    name: str = "read_file"
    description: str = (
        "Le um arquivo do workspace local da execucao. Caminho relativo ao "
        "workspace root (raiz do repo). Use para examinar implementacoes "
        "completas depois que retrieve_knowledge apontou onde olhar."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]
    max_bytes: int = 64 * 1024  # 64 KB

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho relativo ao workspace root (ex: 'app/api/v1/auth.py').",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Linha inicial (1-indexed). Default: 1.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Linha final inclusive. Default: end-of-file.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        rel_path: str = inputs["path"]
        if ctx.workspace_root is None:
            return ToolResult.error("workspace_root nao configurado no contexto")
        full = (ctx.workspace_root / rel_path).resolve()
        # Confine ao workspace
        try:
            full.relative_to(ctx.workspace_root.resolve())
        except ValueError:
            return ToolResult.error(
                f"path '{rel_path}' fora do workspace", code="path_escape"
            )
        if not full.exists():
            return ToolResult.error(f"arquivo nao existe: {rel_path}", code="not_found")
        if not full.is_file():
            return ToolResult.error(f"'{rel_path}' nao e arquivo", code="not_a_file")

        size = full.stat().st_size
        if size > self.max_bytes:
            return ToolResult.error(
                f"arquivo muito grande ({size} bytes > {self.max_bytes})",
                code="too_large",
            )

        text = full.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = int(inputs.get("start_line", 1))
        end_default = len(lines)
        end = int(inputs.get("end_line", end_default))
        start = max(1, start)
        end = min(len(lines), end)
        slice_text = "\n".join(lines[start - 1 : end])
        return ToolResult.ok(
            {
                "path": rel_path,
                "start_line": start,
                "end_line": end,
                "total_lines": len(lines),
                "content": slice_text,
            }
        )


@dataclass
class SignalCompleteTool:
    name: str = "signal_complete"
    description: str = (
        "Sinaliza que a task atual esta CONCLUIDA. Chame essa tool quando voce "
        "tiver entregue tudo que a task pedia. Apos esta chamada, nenhuma outra "
        "acao sera executada nesta task. ATENCAO: se o contexto tem workspace_root, "
        "a tool valida que nao ha commits locais sem push — recusa a conclusao se "
        "houver pendencia. Faca git_push e github_create_pr antes."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Resumo (1-3 linhas) do que foi feito.",
                },
                "deliverables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de entregaveis (PR URL, arquivos criados, etc).",
                },
            },
            "required": ["summary"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        # LEO-52: agentes Dev as vezes chamam signal_complete sem dar git_push
        # ou sem abrir PR, deixando o trabalho em branch local/remota sem PR.
        # Antes de aceitar a conclusao, valida 2 cenarios:
        #   (a) commits sem push       -> error "unpushed_work"
        #   (b) commits pushados mas sem PR_URL nos deliverables -> error "no_pr_url"
        deliverables = inputs.get("deliverables") or []
        if ctx.workspace_root is not None:
            unpushed_reason = await _check_unpushed_work(ctx.workspace_root)
            if unpushed_reason is not None:
                return ToolResult.error(
                    f"signal_complete recusado: {unpushed_reason}. "
                    f"Execute git_push e github_create_pr antes de concluir a task.",
                    code="unpushed_work",
                )

            had_commits = await _had_commits_on_branch(ctx.workspace_root)
            if had_commits and not _contains_pr_url(deliverables):
                # Tambem aceita se Task ja foi linkado a um pr_url (caso o
                # github_create_pr ja persistiu mas o agente esqueceu de citar
                # nos deliverables).
                task_pr_url = await _task_pr_url(ctx)
                if not task_pr_url:
                    return ToolResult.error(
                        "signal_complete recusado: voce fez commits e push, "
                        "mas nao ha PR aberto (deliverables nao tem URL de PR "
                        "e Task.pr_url tambem esta vazio). Chame github_create_pr "
                        "antes de concluir.",
                        code="no_pr_url",
                    )
        return ToolResult.ok(
            {
                "completed": True,
                "summary": inputs.get("summary", ""),
                "deliverables": deliverables,
            }
        )


async def _check_unpushed_work(workspace_root: Path) -> str | None:
    """Verifica se há trabalho local (commits ou changes) ainda não pushado.

    Retorna mensagem descritiva quando há pendência, ou None quando o workspace
    está sincronizado com o remote. Em caso de erro inesperado (ex: sem repo
    git), retorna None — não bloqueia.
    """
    # 1. Working tree limpo? (sem arquivos modificados/uncommited)
    rc, status_out, _ = await _run_git(workspace_root, ["status", "--porcelain"])
    if rc == 0 and status_out.strip():
        files = [ln for ln in status_out.strip().splitlines() if ln.strip()]
        return f"working tree tem {len(files)} arquivo(s) modificado(s) sem commit"

    # 2. Branch tem upstream configurado? (push -u ja feito)
    rc, _, _ = await _run_git(workspace_root, ["rev-parse", "--abbrev-ref", "@{u}"])
    if rc != 0:
        # Sem upstream — branch nunca foi pushada
        # Confirma que há pelo menos 1 commit local (senão é repo vazio)
        rc_log, log_out, _ = await _run_git(workspace_root, ["log", "-1", "--oneline"])
        if rc_log == 0 and log_out.strip():
            return "branch local nunca foi pushada para o remote (sem upstream configurado)"
        return None  # repo sem commits — nao bloqueia

    # 3. Há commits locais não-pushados? (HEAD ahead of upstream)
    rc, count_out, _ = await _run_git(
        workspace_root, ["rev-list", "--count", "@{u}..HEAD"]
    )
    if rc == 0:
        try:
            n = int(count_out.strip())
        except ValueError:
            n = 0
        if n > 0:
            return f"{n} commit(s) local(is) ainda nao pushado(s) para o remote"

    return None


_PR_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/[^/\s]+/[^/\s]+/pull/\d+",
    re.IGNORECASE,
)


def _contains_pr_url(deliverables: list[Any]) -> bool:
    """True se algum item dos deliverables contém uma URL de PR do GitHub."""
    for item in deliverables:
        if isinstance(item, str) and _PR_URL_RE.search(item):
            return True
    return False


async def _had_commits_on_branch(workspace_root: Path) -> bool:
    """True se a branch atual tem commits que não existem na base remota.

    Usa o symbolic-ref upstream pra comparar. Se não há upstream, retorna
    False (sem upstream a função _check_unpushed_work já bloqueou).
    """
    rc, base, _ = await _run_git(
        workspace_root, ["rev-parse", "--abbrev-ref", "@{u}"]
    )
    if rc != 0 or not base.strip():
        return False
    # base esta em formato origin/<branch>. Pega o nome da branch base default
    # do worktree (assume <base>=origin/main quando upstream e a propria branch
    # pushada). Compara commits unicos da branch.
    upstream = base.strip()
    rc, name, _ = await _run_git(workspace_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if rc != 0:
        return False
    branch = name.strip()
    if upstream == f"origin/{branch}":
        # branch foi pushada — verifica se ela diverge de origin/main
        rc, count_out, _ = await _run_git(
            workspace_root, ["rev-list", "--count", "origin/main..HEAD"]
        )
        if rc == 0:
            try:
                return int(count_out.strip()) > 0
            except ValueError:
                return False
    return False


async def _task_pr_url(ctx: AgentRunContext) -> str | None:
    """Lê Task.pr_url do DB (preenchido por github_create_pr)."""
    if ctx.task_id is None:
        return None
    from sqlalchemy import select

    from dev_autonomo.db.models.task import Task

    row = (
        await ctx.session.execute(select(Task).where(Task.id == ctx.task_id))
    ).scalar_one_or_none()
    return row.pr_url if row is not None else None


async def _run_git(
    cwd: Path, args: list[str]
) -> tuple[int, str, str]:
    """Executa `git <args>` em cwd e retorna (returncode, stdout, stderr)."""
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
