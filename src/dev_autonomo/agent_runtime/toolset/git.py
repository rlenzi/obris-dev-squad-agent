"""Tools git: status, branch, diff, commit. Executa `git` no workspace_root."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult


async def _run_git(ctx: AgentRunContext, args: list[str]) -> tuple[int, str, str]:
    """Roda `git <args>` dentro do workspace_root e retorna (returncode, stdout, stderr)."""
    if ctx.workspace_root is None:
        return 1, "", "workspace_root nao configurado"
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(ctx.workspace_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


@dataclass
class GitStatusTool:
    name: str = "git_status"
    description: str = (
        "Lista os arquivos modificados, novos e deletados no workspace. "
        "Use antes de commit pra confirmar o que vai entrar."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {"type": "object", "properties": {}}

    async def execute(self, ctx: AgentRunContext, _inputs: dict[str, Any]) -> ToolResult:
        rc, out, err = await _run_git(ctx, ["status", "--short", "--branch"])
        if rc != 0:
            return ToolResult.error(f"git status falhou: {err}", code="git_error")
        return ToolResult.ok({"output": out.strip()})


@dataclass
class GitBranchTool:
    name: str = "git_branch"
    description: str = (
        "Cria uma branch nova (a partir do HEAD atual) e muda pra ela. "
        "Use no inicio da task pra isolar as mudancas."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nome da branch (ex: 'agent/dev-backend/PAY-1234').",
                },
            },
            "required": ["name"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        branch = inputs["name"]
        rc, out, err = await _run_git(ctx, ["checkout", "-b", branch])
        if rc != 0:
            return ToolResult.error(
                f"git checkout -b falhou: {err.strip() or out.strip()}",
                code="git_error",
            )
        return ToolResult.ok({"branch": branch, "checked_out": True})


@dataclass
class GitDiffTool:
    name: str = "git_diff"
    description: str = (
        "Mostra o diff das mudancas locais (staged ou nao). Use pra revisar antes "
        "de commit."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]
    max_chars: int = 16000

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "default": False,
                    "description": "true = diff de staged only; false = unstaged + untracked",
                },
                "path": {
                    "type": "string",
                    "description": "Limita o diff a um arquivo especifico (opcional).",
                },
            },
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        args = ["diff"]
        if inputs.get("staged"):
            args.append("--cached")
        if inputs.get("path"):
            args.append("--")
            args.append(inputs["path"])
        rc, out, err = await _run_git(ctx, args)
        if rc != 0:
            return ToolResult.error(f"git diff falhou: {err}", code="git_error")
        diff = out
        truncated = False
        if len(diff) > self.max_chars:
            diff = diff[: self.max_chars]
            truncated = True
        return ToolResult.ok({"diff": diff, "truncated": truncated})


@dataclass
class GitCommitTool:
    name: str = "git_commit"
    description: str = (
        "Faz commit de TODAS as mudancas (git add -A primeiro). Use mensagem "
        "no padrao 'tipo: descricao curta' (ex: 'feat: add endpoint /payments')."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Mensagem do commit. Linha 1 ate 72 chars; corpo opcional separado por linha vazia.",
                },
            },
            "required": ["message"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        message: str = inputs["message"]
        # add tudo (inclusive arquivos novos)
        rc, _, err = await _run_git(ctx, ["add", "-A"])
        if rc != 0:
            return ToolResult.error(f"git add falhou: {err}", code="git_error")
        # commit
        rc, out, err = await _run_git(ctx, ["commit", "-m", message])
        if rc != 0:
            # caso comum: nothing to commit
            full = (out + err).strip()
            return ToolResult.error(
                f"git commit falhou: {full[:300]}", code="git_error"
            )
        # pega o hash do HEAD pra retornar
        rc2, sha, _ = await _run_git(ctx, ["rev-parse", "HEAD"])
        return ToolResult.ok(
            {
                "committed": True,
                "message": message,
                "sha": sha.strip() if rc2 == 0 else None,
            }
        )
