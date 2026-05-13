"""Base do toolset: contratos, registry, contexto compartilhado.

Cada tool implementa Tool. O ToolRegistry expõe a lista no formato esperado
pelo Claude tool_use API e faz dispatch quando Claude pede um tool_use.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolResult:
    """Resultado da execução de uma tool. Vira tool_result do Claude API."""

    content: str  # Texto que volta pra Claude (geralmente JSON serializado)
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any) -> ToolResult:
        if isinstance(data, (dict, list)):
            content = json.dumps(data, default=str, ensure_ascii=False)
        else:
            content = str(data)
        return cls(content=content, is_error=False)

    @classmethod
    def error(cls, message: str, *, code: str | None = None) -> ToolResult:
        payload: dict[str, Any] = {"error": message}
        if code:
            payload["code"] = code
        return cls(content=json.dumps(payload), is_error=True)


@runtime_checkable
class Tool(Protocol):
    """Interface que toda tool deve implementar."""

    name: str
    description: str
    input_schema: dict[str, Any]

    async def execute(self, ctx: Any, inputs: dict[str, Any]) -> ToolResult: ...


@dataclass
class ToolRegistry:
    """Catálogo de tools disponíveis pra um agente. Filtra por nome (enabled)."""

    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def schemas(self, enabled_names: list[str] | None = None) -> list[dict[str, Any]]:
        """Retorna os schemas no formato pro Anthropic API.

        Se `enabled_names` for fornecido, filtra. Sem filtro = todas as registradas.
        """
        selected = (
            [self.tools[n] for n in enabled_names if n in self.tools]
            if enabled_names is not None
            else list(self.tools.values())
        )
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in selected
        ]

    async def dispatch(
        self,
        name: str,
        inputs: dict[str, Any],
        ctx: Any,
        *,
        enabled_names: list[str] | None = None,
    ) -> ToolResult:
        """Executa uma tool por nome. Falha se nao registrada ou desabilitada."""
        if enabled_names is not None and name not in enabled_names:
            return ToolResult.error(
                f"tool '{name}' nao habilitada para este agente",
                code="tool_disabled",
            )
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult.error(
                f"tool '{name}' nao registrada", code="tool_not_found"
            )
        try:
            return await tool.execute(ctx, inputs)
        except Exception as exc:
            logger.exception("tool %s falhou", name)
            return ToolResult.error(
                f"{type(exc).__name__}: {exc}", code="tool_exception"
            )
