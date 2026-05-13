"""Worker do Agent Runtime: loop Claude tool_use ate signal_complete ou max_turns.

Fase 3.1a: versão mínima que recebe um prompt, executa o loop, retorna resultado.
Fase 3.1d: passa a consumir RabbitMQ em vez de receber prompt direto.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class AgentRunResult:
    completed: bool
    final_text: str
    turn_count: int
    tool_calls: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    error: str | None = None
    completion_summary: str | None = None
    completion_deliverables: list[str] = field(default_factory=list)


class AgentRunner:
    """Roda um agente em um loop de tool_use ate completar ou esgotar turnos."""

    def __init__(
        self,
        ctx: AgentRunContext,
        registry: ToolRegistry,
        *,
        model: str = "claude-haiku-4-5",
        max_turns: int = 12,
        max_tokens_per_turn: int = 4096,
    ) -> None:
        self.ctx = ctx
        self.registry = registry
        self.model = model
        self.max_turns = max_turns
        self.max_tokens_per_turn = max_tokens_per_turn

    async def run(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        enabled_tools: list[str],
    ) -> AgentRunResult:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt},
        ]
        tools_schema = self.registry.schemas(enabled_tools)
        tool_calls: list[str] = []
        total_cost = 0.0

        for turn in range(1, self.max_turns + 1):
            response = await self.ctx.claude.complete(
                model=self.model,
                system=system_prompt,
                messages=messages,
                max_tokens=self.max_tokens_per_turn,
                client_id=self.ctx.client_id,
                task_id=self.ctx.task_id,
                agent_instance_id=self.ctx.agent_instance_id,
                extra_kwargs={"tools": tools_schema} if tools_schema else None,
            )
            total_cost += float(response.cost_usd)
            self.ctx.cost_usd_total += float(response.cost_usd)

            raw = response.raw
            stop_reason = raw.stop_reason
            logger.info(
                "Turn %d: stop_reason=%s tokens_in=%d tokens_out=%d cost=$%.4f",
                turn,
                stop_reason,
                response.input_tokens,
                response.output_tokens,
                float(response.cost_usd),
            )

            # Adiciona resposta do Claude no historico
            messages.append({"role": "assistant", "content": raw.content})

            if stop_reason == "end_turn":
                # Claude terminou sem chamar tool — coleta texto e retorna
                final_text = self._concat_text(raw.content)
                return AgentRunResult(
                    completed=False,
                    final_text=final_text,
                    turn_count=turn,
                    tool_calls=tool_calls,
                    total_cost_usd=total_cost,
                )

            if stop_reason == "tool_use":
                tool_results_blocks: list[dict[str, Any]] = []
                completion_block: dict[str, Any] | None = None
                for block in raw.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    tool_name = block.name
                    tool_input = dict(block.input or {})
                    tool_calls.append(tool_name)
                    self.ctx.tools_invoked.append(tool_name)
                    logger.info("  -> tool_use: %s(%s)", tool_name, list(tool_input.keys()))

                    result = await self.registry.dispatch(
                        tool_name, tool_input, self.ctx, enabled_names=enabled_tools
                    )
                    tool_results_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result.content,
                            "is_error": result.is_error,
                        }
                    )
                    # Se foi signal_complete, captura
                    if tool_name == "signal_complete" and not result.is_error:
                        try:
                            payload = json.loads(result.content)
                            completion_block = payload
                        except json.JSONDecodeError:
                            completion_block = {"summary": result.content}

                messages.append({"role": "user", "content": tool_results_blocks})

                if completion_block is not None:
                    return AgentRunResult(
                        completed=True,
                        final_text=completion_block.get("summary", ""),
                        turn_count=turn,
                        tool_calls=tool_calls,
                        total_cost_usd=total_cost,
                        completion_summary=completion_block.get("summary"),
                        completion_deliverables=completion_block.get("deliverables", []),
                    )

                continue  # próximo turno

            # Outros stop_reasons (max_tokens, refusal, etc) — encerra
            logger.warning("Stop reason inesperado: %s — encerrando", stop_reason)
            return AgentRunResult(
                completed=False,
                final_text=self._concat_text(raw.content),
                turn_count=turn,
                tool_calls=tool_calls,
                total_cost_usd=total_cost,
                error=f"stop_reason: {stop_reason}",
            )

        # Esgotou max_turns
        return AgentRunResult(
            completed=False,
            final_text="",
            turn_count=self.max_turns,
            tool_calls=tool_calls,
            total_cost_usd=total_cost,
            error=f"max_turns ({self.max_turns}) atingido sem signal_complete",
        )

    @staticmethod
    def _concat_text(content: list[Any]) -> str:
        return "".join(
            block.text for block in content if getattr(block, "type", None) == "text"
        )
