"""Tool stack-agnóstica para o Dev executar checks declarados pelo repo.

O agente Dev historicamente só escrevia código sem rodar nada — abria PR
baseado em "leitura do código". Esta tool fecha esse gap **sem hard-coding
de stack**: ela lê `.dev-autonomo.yml` da raiz do worktree e executa o
comando declarado para o check pedido.

Cada cliente declara no seu próprio repo (`.dev-autonomo.yml`):

```yaml
version: 1
stack: "node+express"
commands:
  install:   "npm ci"
  lint:      "npm run lint"
  typecheck: "npm run typecheck"
  test:      "npm test -- --runInBand"
```

A plataforma não conhece npm/pytest/gradle — ela apenas executa o que
está declarado. Novos clientes com stacks diferentes funcionam sem
mudança no código da plataforma.

Restrições de segurança:
- Só executa comandos da lista declarada em `commands` do yml.
- Não aceita comando arbitrário do agente.
- Timeout configurável (default 5min) pra evitar runs eternas.
- Stdout/stderr truncados em ~32KB cada pra não estourar contexto.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.toolset.base import ToolResult

REPO_DESCRIPTOR_FILENAME = ".dev-autonomo.yml"
MAX_OUTPUT_BYTES = 32 * 1024
DEFAULT_TIMEOUT_SECONDS = 300  # 5 min

# Lista de checks suportados. O Dev pode pedir qualquer um destes; o yml
# do repo declara quais estão configurados (vazio = skip).
SUPPORTED_CHECKS = {"install", "lint", "typecheck", "test", "build"}


@dataclass
class RunRepoCheckTool:
    name: str = "run_repo_check"
    description: str = (
        "Executa um check declarado no .dev-autonomo.yml do repo (install, "
        "lint, typecheck, test ou build). Use ANTES de fazer commit/push pra "
        "validar que sua mudanca nao quebrou o codigo. O comando real "
        "executado depende do stack declarado pelo cliente (Python, Node, "
        "Java, Go, etc) — esta tool e stack-agnostica. Retorna stdout, "
        "stderr e exit_code."
    )
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.input_schema = {
            "type": "object",
            "properties": {
                "check": {
                    "type": "string",
                    "enum": sorted(SUPPORTED_CHECKS),
                    "description": (
                        "Nome do check a executar. Deve estar declarado no "
                        ".dev-autonomo.yml com comando nao-vazio."
                    ),
                },
                "timeout_seconds": {
                    "type": "integer",
                    "default": DEFAULT_TIMEOUT_SECONDS,
                    "minimum": 10,
                    "maximum": 1800,
                    "description": (
                        "Timeout em segundos. Default 300 (5min). "
                        "Max 1800 (30min) — checks longos devem ser quebrados."
                    ),
                },
            },
            "required": ["check"],
        }

    async def execute(self, ctx: AgentRunContext, inputs: dict[str, Any]) -> ToolResult:
        if ctx.workspace_root is None:
            return ToolResult.error(
                "workspace_root nao configurado no contexto",
                code="no_workspace",
            )

        check: str = inputs["check"]
        if check not in SUPPORTED_CHECKS:
            return ToolResult.error(
                f"check '{check}' nao suportado. Use um de: {sorted(SUPPORTED_CHECKS)}",
                code="bad_input",
            )

        # Lê descriptor do repo (yml na raiz do worktree)
        descriptor_path = ctx.workspace_root / REPO_DESCRIPTOR_FILENAME
        if not descriptor_path.exists():
            return ToolResult.error(
                f"{REPO_DESCRIPTOR_FILENAME} nao encontrado em {ctx.workspace_root}. "
                "Cliente precisa declarar como rodar os checks no repo.",
                code="no_descriptor",
            )

        try:
            descriptor = _load_yaml(descriptor_path)
        except Exception as exc:
            return ToolResult.error(
                f"{REPO_DESCRIPTOR_FILENAME} invalido: {exc}",
                code="bad_descriptor",
            )

        commands = descriptor.get("commands") or {}
        cmd = (commands.get(check) or "").strip()
        if not cmd:
            return ToolResult.ok(
                {
                    "check": check,
                    "skipped": True,
                    "reason": f"comando '{check}' nao declarado no {REPO_DESCRIPTOR_FILENAME}",
                    "stack": descriptor.get("stack"),
                }
            )

        timeout = int(inputs.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
        timeout = max(10, min(timeout, 1800))

        rc, stdout, stderr, duration_ms, timed_out = await _run_shell(
            cmd, cwd=ctx.workspace_root, timeout=timeout
        )

        return ToolResult.ok(
            {
                "check": check,
                "stack": descriptor.get("stack"),
                "command": cmd,
                "exit_code": rc,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "stdout": _truncate(stdout, MAX_OUTPUT_BYTES),
                "stderr": _truncate(stderr, MAX_OUTPUT_BYTES),
                "passed": rc == 0 and not timed_out,
            }
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    """Carrega o yml. Tenta PyYAML primeiro; se não disponível, parser minimal."""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        # Fallback minimal: extrai apenas a seção `commands` via parsing linha-a-linha.
        # Suficiente para esta tool, mas o PyYAML deve estar nas dependências.
        return _yaml_minimal_parse(path.read_text(encoding="utf-8"))


def _yaml_minimal_parse(text: str) -> dict:
    """Parser minimal de YAML — extrai apenas chaves top-level + bloco commands.

    NÃO substitui PyYAML — fallback para garantir funcionamento se a lib
    não estiver instalada. Cobre estrutura típica do .dev-autonomo.yml.
    """
    result: dict = {"commands": {}}
    in_commands = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            in_commands = line.strip().startswith("commands:")
            if ":" in line and not in_commands:
                k, _, v = line.partition(":")
                v = v.strip().strip('"').strip("'")
                if v:
                    result[k.strip()] = v
            continue
        # linha indentada
        if in_commands and ":" in line:
            stripped = line.strip()
            k, _, v = stripped.partition(":")
            v = v.strip().strip('"').strip("'")
            result["commands"][k.strip()] = v
    return result


async def _run_shell(
    command: str, cwd: Path, timeout: int
) -> tuple[int, str, str, int, bool]:
    """Executa shell command, retorna (rc, stdout, stderr, duration_ms, timed_out)."""
    import time

    start = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        timed_out = False
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return (
            -1,
            "",
            f"[run_repo_check] command timed out after {timeout}s",
            int((time.monotonic() - start) * 1000),
            True,
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    rc = proc.returncode or 0
    return (
        rc,
        stdout_b.decode("utf-8", errors="replace"),
        stderr_b.decode("utf-8", errors="replace"),
        duration_ms,
        timed_out,
    )


def _truncate(text: str, max_bytes: int) -> str:
    if not text:
        return text
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    # corta no max_bytes e adiciona marcador
    truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
    return truncated + f"\n... [output truncado em {max_bytes} bytes]"
