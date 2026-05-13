"""Tools de escrita de arquivos: edit_file, create_file, delete_file.

Toda escrita passa pelo ManifestEnforcer (camada 3 da defesa em profundidade).
Path eh sempre confinado ao workspace_root + repo do contexto.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult


def _resolve_path(ctx: AgentRunContext, rel_path: str) -> Path | None:
    """Resolve rel_path dentro do workspace; retorna None se escapar."""
    if ctx.workspace_root is None:
        return None
    root = ctx.workspace_root.resolve()
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


async def _enforce_or_block(
    ctx: AgentRunContext, tool_name: str, rel_path: str
) -> ToolResult | None:
    """Aplica check_edit_file via enforcer; loga e retorna ToolResult de bloqueio se nao autorizado."""
    repo_id = ctx.workspace_repo or ""
    if not repo_id:
        return ToolResult.error(
            "workspace_repo nao configurado no contexto", code="no_repo"
        )
    result = await ctx.enforcer.check_edit_file(repo=repo_id, file_path=rel_path)
    await ctx.enforcer.authorize(tool_name, f"{repo_id}:{rel_path}", result)
    if not result.allowed:
        return ToolResult.error(
            result.suggestion or "tool call bloqueada pelo manifest",
            code=result.reason,
        )
    return None


@dataclass
class EditFileTool:
    name: str = "edit_file"
    description: str = (
        "Edita um arquivo existente. Dois modos: 'replace' (busca string exata e "
        "substitui — preferido pra mudancas pequenas) ou 'rewrite' (substitui o "
        "arquivo INTEIRO — use somente quando todo o conteudo precisar mudar). "
        "Passa pelo enforce do manifest da squad antes de gravar."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho relativo ao workspace_root.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "rewrite"],
                    "description": "'replace' = search+replace; 'rewrite' = sobrescreve tudo.",
                },
                "search": {
                    "type": "string",
                    "description": "(modo replace) string EXATA a buscar — incluindo whitespace.",
                },
                "replacement": {
                    "type": "string",
                    "description": "(modo replace) string que substitui a busca.",
                },
                "new_content": {
                    "type": "string",
                    "description": "(modo rewrite) novo conteudo completo do arquivo.",
                },
            },
            "required": ["path", "mode"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        rel_path: str = inputs["path"]
        mode: str = inputs["mode"]

        blocked = await _enforce_or_block(ctx, self.name, rel_path)
        if blocked is not None:
            return blocked

        target = _resolve_path(ctx, rel_path)
        if target is None:
            return ToolResult.error(
                f"path '{rel_path}' fora do workspace", code="path_escape"
            )
        if not target.exists():
            return ToolResult.error(
                f"arquivo nao existe: {rel_path}. Use create_file para novos.",
                code="not_found",
            )

        if mode == "replace":
            search = inputs.get("search")
            replacement = inputs.get("replacement")
            if search is None or replacement is None:
                return ToolResult.error(
                    "modo 'replace' exige 'search' e 'replacement'",
                    code="invalid_input",
                )
            original = target.read_text(encoding="utf-8")
            count = original.count(search)
            if count == 0:
                return ToolResult.error(
                    "string 'search' nao encontrada no arquivo",
                    code="search_not_found",
                )
            if count > 1:
                return ToolResult.error(
                    f"string 'search' encontrada {count}x. Inclua mais contexto pra ficar unica.",
                    code="ambiguous_search",
                )
            new = original.replace(search, replacement, 1)
            target.write_text(new, encoding="utf-8")
            return ToolResult.ok(
                {
                    "path": rel_path,
                    "mode": mode,
                    "old_len": len(original),
                    "new_len": len(new),
                    "delta": len(new) - len(original),
                }
            )

        if mode == "rewrite":
            new_content = inputs.get("new_content")
            if new_content is None:
                return ToolResult.error(
                    "modo 'rewrite' exige 'new_content'", code="invalid_input"
                )
            original_size = target.stat().st_size
            target.write_text(new_content, encoding="utf-8")
            return ToolResult.ok(
                {
                    "path": rel_path,
                    "mode": mode,
                    "old_len": original_size,
                    "new_len": len(new_content),
                    "delta": len(new_content) - original_size,
                }
            )

        return ToolResult.error(f"mode invalido: {mode}", code="invalid_input")


@dataclass
class CreateFileTool:
    name: str = "create_file"
    description: str = (
        "Cria um arquivo novo no workspace. Falha se ja existir. Passa pelo "
        "enforce do manifest."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho relativo ao workspace_root.",
                },
                "content": {
                    "type": "string",
                    "description": "Conteudo completo do arquivo.",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        rel_path: str = inputs["path"]
        content: str = inputs["content"]

        blocked = await _enforce_or_block(ctx, self.name, rel_path)
        if blocked is not None:
            return blocked

        target = _resolve_path(ctx, rel_path)
        if target is None:
            return ToolResult.error(
                f"path '{rel_path}' fora do workspace", code="path_escape"
            )
        if target.exists():
            return ToolResult.error(
                f"arquivo ja existe: {rel_path}. Use edit_file pra modificar.",
                code="already_exists",
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult.ok({"path": rel_path, "bytes": len(content.encode("utf-8"))})


@dataclass
class DeleteFileTool:
    name: str = "delete_file"
    description: str = (
        "Remove um arquivo do workspace. Use com cuidado. Passa pelo enforce."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Caminho relativo ao workspace_root.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        rel_path: str = inputs["path"]

        blocked = await _enforce_or_block(ctx, self.name, rel_path)
        if blocked is not None:
            return blocked

        target = _resolve_path(ctx, rel_path)
        if target is None:
            return ToolResult.error(
                f"path '{rel_path}' fora do workspace", code="path_escape"
            )
        if not target.exists():
            return ToolResult.error(f"arquivo nao existe: {rel_path}", code="not_found")
        if not target.is_file():
            return ToolResult.error(f"'{rel_path}' nao e arquivo", code="not_a_file")

        target.unlink()
        return ToolResult.ok({"path": rel_path, "deleted": True})
