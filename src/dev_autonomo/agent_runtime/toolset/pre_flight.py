"""Tool de pre-flight: valida que arquivos modificados pelo Dev casam com o
skeleton declarado pelo Architect na issue Jira.

Motivacao (LEO-21): em runs reais o Dev as vezes inventa caminhos de
arquivo, cria arquivos fora do escopo decidido pelo Architect, ou esquece
de criar arquivos previstos. O Reviewer pega isso mas custa um ciclo
extra. Pre-flight da feedback imediato no proprio run do Dev.

Como funciona:
- O Architect, ao criar subtask via jira_create_subtask, inclui um bloco
  "## Pre-flight Skeleton" na description listando os arquivos previstos.
- O Dev, antes de git_commit, chama pre_flight_check. A tool:
  1. Le a description da issue (campo description do Task, ja persistido
     OU faz jira_get_issue se precisar).
  2. Extrai a lista de paths da secao "Pre-flight Skeleton".
  3. Compara com files atualmente alterados no worktree (git status).
  4. Retorna: passed, missing (skeleton declarou mas Dev nao mexeu),
     extra (Dev mexeu mas nao estava no skeleton).

Formato esperado da secao no Jira (markdown):

```
## Pre-flight Skeleton
- path/to/file1.py — nova funcao foo()
- path/to/file2.tsx — adicionar prop X em ComponentY
```

Cada linha deve comecar com `-` seguido do path. O texto apos `—` ou `:`
e opcional (descricao livre).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult
from dev_autonomo.db.models.task import Task

SKELETON_HEADER_RE = re.compile(r"^\s*##\s+Pre-?flight\s+Skeleton\s*$", re.IGNORECASE)
PATH_LINE_RE = re.compile(r"^\s*[-*]\s+`?([^\s`—:]+)`?\s*(?:[—:].*)?$")


@dataclass
class PreFlightCheckTool:
    name: str = "pre_flight_check"
    description: str = (
        "Valida que os arquivos modificados no worktree casam com o "
        "Pre-flight Skeleton declarado pelo Architect na description da "
        "issue Jira. Use ANTES de git_commit pra pegar drift cedo. "
        "Retorna passed (bool), missing_from_changes (declarados mas nao "
        "alterados) e extra_in_changes (alterados mas nao declarados). "
        "Drift nao e bloqueante automatico — voce decide se justifica "
        "via comentario Jira ou ajusta os arquivos."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "issue_description": {
                    "type": "string",
                    "description": (
                        "Opcional: description da issue Jira ja em mao. "
                        "Se nao informado, a tool tenta ler do Task local."
                    ),
                },
            },
            "required": [],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if ctx.workspace_root is None:
            return ToolResult.error(
                "workspace_root nao configurado — pre_flight_check so "
                "faz sentido em agentes com worktree (Dev).",
                code="no_workspace",
            )

        # 1. Pega description da issue
        description = (inputs.get("issue_description") or "").strip()
        if not description and ctx.task_id is not None:
            row = (
                await ctx.session.execute(select(Task).where(Task.id == ctx.task_id))
            ).scalar_one_or_none()
            if row is not None and row.title:
                # Task.title nao traz description completa. Por ora, sem
                # description fornecida + sem cache, retornamos warning.
                description = ""

        if not description:
            return ToolResult.ok(
                {
                    "passed": False,
                    "reason": (
                        "issue_description nao fornecida e nao ha description "
                        "cacheada no Task local. Passe a description via "
                        "argumento ou chame jira_get_issue antes."
                    ),
                    "skeleton_paths": [],
                    "changed_paths": [],
                    "missing_from_changes": [],
                    "extra_in_changes": [],
                }
            )

        # 2. Extrai paths do skeleton
        skeleton_paths = _extract_skeleton_paths(description)

        # 3. Lista arquivos alterados (git status --porcelain)
        changed_paths = await _list_changed_files(ctx.workspace_root)

        # 4. Diff
        skeleton_set = set(skeleton_paths)
        changed_set = set(changed_paths)
        missing = sorted(skeleton_set - changed_set)
        extra = sorted(changed_set - skeleton_set)
        passed = not missing and not extra

        return ToolResult.ok(
            {
                "passed": passed,
                "skeleton_paths": skeleton_paths,
                "changed_paths": sorted(changed_paths),
                "missing_from_changes": missing,
                "extra_in_changes": extra,
                "guidance": _guidance(passed, missing, extra, skeleton_paths),
            }
        )


def _extract_skeleton_paths(description: str) -> list[str]:
    """Extrai paths da secao '## Pre-flight Skeleton' da description.

    Para no primeiro `## ` seguinte que nao seja a propria secao.
    """
    lines = description.splitlines()
    paths: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.rstrip()
        if SKELETON_HEADER_RE.match(stripped):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## "):
                # outra secao H2 — sair
                break
            m = PATH_LINE_RE.match(stripped)
            if m:
                path = m.group(1).strip().strip("`").strip(",")
                if path and not path.startswith("#"):
                    paths.append(path)
    return paths


async def _list_changed_files(workspace_root: Path) -> list[str]:
    """Retorna a lista de paths modificados/adicionados no worktree."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        "status",
        "--porcelain",
        cwd=str(workspace_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, _ = await proc.communicate()
    out = stdout_b.decode("utf-8", errors="replace")
    paths: list[str] = []
    for raw in out.splitlines():
        if len(raw) < 4:
            continue
        # Format: "XY path" ou "XY orig -> new" para rename
        rest = raw[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.append(rest)
    return paths


def _guidance(
    passed: bool,
    missing: list[str],
    extra: list[str],
    skeleton: list[str],
) -> str:
    if passed and skeleton:
        return "Skeleton bate com as mudancas. Pode commitar."
    if passed and not skeleton:
        return (
            "Nao encontrei 'Pre-flight Skeleton' na issue. Architect pode nao "
            "ter declarado — siga em frente."
        )
    parts = []
    if missing:
        parts.append(
            f"Arquivos declarados no skeleton mas que voce ainda nao mexeu: "
            f"{', '.join(missing)}. Crie/edite ou justifique no comentario "
            f"Jira se intencionalmente fora de escopo."
        )
    if extra:
        parts.append(
            f"Arquivos modificados fora do skeleton: {', '.join(extra)}. "
            f"Se sao mudancas conscientes, OK — mas explique no PR body."
        )
    return " ".join(parts)
