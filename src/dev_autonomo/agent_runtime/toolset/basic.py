"""Tools básicas da Fase 3.1a: retrieve_knowledge, read_file, signal_complete."""

from __future__ import annotations

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
        "acao sera executada nesta task."
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
        return ToolResult.ok(
            {
                "completed": True,
                "summary": inputs.get("summary", ""),
                "deliverables": inputs.get("deliverables", []),
            }
        )
