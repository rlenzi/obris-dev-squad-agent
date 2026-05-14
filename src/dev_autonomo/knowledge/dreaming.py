"""Dreaming — consolidação assíncrona de memória entre sessões.

Status (2026-05-14): Dreaming é **research preview** da Anthropic.
- SDK 0.102.0 NÃO expõe ``c.beta.dreams``.
- Acesso requer request via form em ``claude.com/form/claude-managed-agents``.
- Beta header esperado: ``dreaming-2026-04-21``.

Este módulo está **pré-pronto** para ativação automática quando uma das
duas condições ocorrer:
1. SDK adiciona ``c.beta.dreams.create`` → ``is_available()`` retorna True
   e ``consolidate()`` chama via SDK normal.
2. SDK não adicionado mas conta tem access → ``is_available()`` retorna
   False mas ``consolidate()`` consegue via raw HTTP. Caller pode forçar
   tentativa via ``allow_raw_http=True``.

Em ambos os casos, o resto do sistema (hook pós-task, persistência de
DreamConsolidationResult, etc) não muda — só este módulo precisa ser
atualizado quando a API estabilizar.

**Fluxo conceitual:**
    1. Task termina → managed_runner registra usage e session.id.
    2. Hook pós-task (a implementar) chama:
        ``dreaming.consolidate(
            memory_store_id=<store da squad>,
            session_ids=[<sessão recém-fechada>, ...lote],
            instructions="Foco em padrões reutilizáveis pra próximos runs.",
        )``
    3. Output: novo memory_store_id consolidado. Sistema pode promover pra
       partição playbook ou apenas substituir o store atual.

**Custo previsto** (segundo doc Anthropic, sob nosso billing):
    Opus 4.7 ou Sonnet 4.6, token rate padrão. Sem fee extra de
    consolidação. Escala linear com sessões + tamanho.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import anthropic

from dev_autonomo.common.claude_pricing import get_pricing
from dev_autonomo.config import get_settings

logger = logging.getLogger(__name__)

DREAMING_BETA_HEADER = "dreaming-2026-04-21"
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass(slots=True)
class DreamConsolidationResult:
    """Resultado de uma consolidação via Dreaming.

    Quando ``status == "skipped_unavailable"``, ``output_memory_store_id``
    é None e nada foi cobrado.
    """

    status: str  # "completed" | "running" | "failed" | "skipped_unavailable"
    dream_id: str | None = None
    output_memory_store_id: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    error: str | None = None
    raw: Any = None


def is_available(anthropic_client: anthropic.Anthropic | None = None) -> bool:
    """Detecta se Dreaming está acessível via SDK no momento.

    Verifica ``c.beta.dreams``. Não faz request HTTP — apenas inspeciona
    o cliente. False não significa que sua conta não tem access; pode
    significar só que SDK ainda não wrappeou o endpoint.
    """
    client = anthropic_client or _build_client()
    return hasattr(client.beta, "dreams")


def consolidate(
    *,
    memory_store_id: str,
    session_ids: list[str],
    instructions: str | None = None,
    model: str = DEFAULT_MODEL,
    anthropic_client: anthropic.Anthropic | None = None,
    allow_raw_http: bool = False,
) -> DreamConsolidationResult:
    """Dispara uma consolidação Dreaming.

    Args:
        memory_store_id: store de input + onde insights vão.
        session_ids: lista (até 100) de sessions a revisitar.
        instructions: até 4096 chars, foco da consolidação.
        model: claude-opus-4-7 ou claude-sonnet-4-6.
        anthropic_client: opcional, default cria do settings.
        allow_raw_http: se SDK não tem ``beta.dreams`` mas você quer
            tentar via raw HTTP (caso conta tenha access mesmo sem
            wrapper liberado). Default False — retorna skipped.

    Returns:
        DreamConsolidationResult. Caller decide o que fazer (gravar em
        DB, promover store, alertar humano, etc).
    """
    if not session_ids:
        raise ValueError("session_ids vazio")
    if len(session_ids) > 100:
        raise ValueError(f"max 100 sessions por dream, recebido {len(session_ids)}")

    client = anthropic_client or _build_client()

    if hasattr(client.beta, "dreams"):
        return _consolidate_via_sdk(
            client, memory_store_id, session_ids, instructions, model
        )

    if allow_raw_http:
        return _consolidate_via_raw_http(
            client, memory_store_id, session_ids, instructions, model
        )

    return DreamConsolidationResult(
        status="skipped_unavailable",
        error=(
            "Dreaming não disponível no SDK atual (anthropic "
            f"{anthropic.__version__}). Pra forçar tentativa via raw HTTP, "
            "passe allow_raw_http=True. Pra request access, ver "
            "https://claude.com/form/claude-managed-agents."
        ),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_settings().ANTHROPIC_API_KEY.get_secret_value()
    )


def _consolidate_via_sdk(
    client: anthropic.Anthropic,
    memory_store_id: str,
    session_ids: list[str],
    instructions: str | None,
    model: str,
) -> DreamConsolidationResult:
    """Chama via SDK quando ``client.beta.dreams`` existir.

    Síncrono via polling — Dreaming é job assíncrono no servidor.
    """
    inputs = [
        {"type": "memory_store", "memory_store_id": memory_store_id},
        {"type": "sessions", "session_ids": session_ids},
    ]
    create_kwargs: dict[str, Any] = {
        "inputs": inputs,
        "model": model,
        "betas": [DREAMING_BETA_HEADER],
    }
    if instructions:
        create_kwargs["instructions"] = instructions[:4096]

    dream = client.beta.dreams.create(**create_kwargs)
    logger.info("dreaming: job criado dream_id=%s", dream.id)

    final = _poll_until_terminal(client, dream.id)
    return _result_from_dream_object(final, model)


def _consolidate_via_raw_http(
    client: anthropic.Anthropic,
    memory_store_id: str,
    session_ids: list[str],
    instructions: str | None,
    model: str,
) -> DreamConsolidationResult:
    """Fallback: chama POST /v1/dreams direto via httpx do cliente.

    Caminho de escape pra quando endpoint está liberado pra conta mas
    SDK ainda não wrappeou. Usa ``client._client.post`` (private API).
    """
    payload: dict[str, Any] = {
        "inputs": [
            {"type": "memory_store", "memory_store_id": memory_store_id},
            {"type": "sessions", "session_ids": session_ids},
        ],
        "model": model,
    }
    if instructions:
        payload["instructions"] = instructions[:4096]

    extra_headers = {
        "anthropic-beta": DREAMING_BETA_HEADER,
    }

    try:
        response = client._client.post(  # type: ignore[attr-defined]
            "/v1/dreams",
            json=payload,
            headers=extra_headers,
        )
    except Exception as exc:
        return DreamConsolidationResult(
            status="failed",
            error=f"raw http create falhou: {type(exc).__name__}: {exc}",
        )

    if response.status_code >= 400:
        return DreamConsolidationResult(
            status="failed",
            error=f"HTTP {response.status_code}: {response.text[:300]}",
        )

    data = response.json()
    dream_id = data.get("id")
    if not dream_id:
        return DreamConsolidationResult(
            status="failed",
            error=f"resposta sem id: {data}",
        )

    final = _poll_raw_until_terminal(client, dream_id)
    return _result_from_dict(final, model)


def _poll_until_terminal(
    client: anthropic.Anthropic, dream_id: str, max_wait_s: int = 600
) -> Any:
    """Polling via SDK."""
    import time

    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        dream = client.beta.dreams.retrieve(dream_id)  # type: ignore[attr-defined]
        status = getattr(dream, "status", None)
        if status in ("completed", "failed", "canceled"):
            return dream
        time.sleep(10)
    raise TimeoutError(f"dream {dream_id} não terminou em {max_wait_s}s")


def _poll_raw_until_terminal(
    client: anthropic.Anthropic, dream_id: str, max_wait_s: int = 600
) -> dict[str, Any]:
    """Polling via raw HTTP."""
    import time

    extra_headers = {"anthropic-beta": DREAMING_BETA_HEADER}
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        response = client._client.get(  # type: ignore[attr-defined]
            f"/v1/dreams/{dream_id}", headers=extra_headers,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") in ("completed", "failed", "canceled"):
            return data
        time.sleep(10)
    raise TimeoutError(f"dream {dream_id} não terminou em {max_wait_s}s")


def _result_from_dream_object(dream: Any, model: str) -> DreamConsolidationResult:
    """Extrai resultado quando vier de SDK object."""
    status = getattr(dream, "status", "unknown")
    dream_id = getattr(dream, "id", None)
    outputs = getattr(dream, "outputs", []) or []
    out_store_id = None
    for o in outputs:
        if getattr(o, "type", None) == "memory_store":
            out_store_id = getattr(o, "memory_store_id", None)
            break

    usage = getattr(dream, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
    cost = _estimate_cost(model, input_tokens, output_tokens)

    return DreamConsolidationResult(
        status=status,
        dream_id=dream_id,
        output_memory_store_id=out_store_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        raw=dream,
    )


def _result_from_dict(data: dict[str, Any], model: str) -> DreamConsolidationResult:
    """Extrai resultado quando vier de raw HTTP dict."""
    out_store_id = None
    for o in data.get("outputs", []) or []:
        if o.get("type") == "memory_store":
            out_store_id = o.get("memory_store_id")
            break

    usage = data.get("usage") or {}
    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    cost = _estimate_cost(model, input_tokens, output_tokens)

    return DreamConsolidationResult(
        status=data.get("status", "unknown"),
        dream_id=data.get("id"),
        output_memory_store_id=out_store_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        raw=data,
    )


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    try:
        pricing = get_pricing(model, provider="anthropic")
        return pricing.cost_usd(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )
    except Exception:
        # Pricing pode não cobrir Dreaming yet — retornar 0 em vez de quebrar.
        return Decimal("0")
